import json
import sys
import os
import logging
import traceback
import pandas as pd
import time
from typing import Dict, Any

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)
from scripts.sql.generator import SQLGeneratorBedrock, SQLGeneratorHF
from scripts.config import LLM_CONF
from scripts.utils import s3_key_exists, s3, log_error

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
logger.setLevel(logging.INFO)


class SQLGenerationError(Exception):
    """Custom exception for SQL generation errors"""

    pass


class DatabaseError(Exception):
    """Custom exception for database operation errors"""

    pass


def validate_input(body: Dict[str, Any]) -> None:
    """Validate required input parameters"""
    required_fields = [
        "model_id",
        "approach",
        "database_type",
        "db_conn_conf",
        "question",
    ]
    missing_fields = [field for field in required_fields if not body.get(field)]

    if missing_fields:
        raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")


def format_error_response(error: Exception, status_code: int = 500) -> Dict[str, Any]:
    """Format error response"""
    error_type = type(error).__name__
    error_message = str(error)

    logger.error(f"{error_type}: {error_message}")
    logger.error(traceback.format_exc())

    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps({"error": {"type": error_type, "message": error_message}}),
    }


def lambda_handler(event, context):
    print('QueryBot Lambda invoked')
    
    try:
        try:
            body = event
            validate_input(body)
        except (json.JSONDecodeError, ValueError) as e:
            return format_error_response(e, 400)
        S3_BUCKET = os.environ.get("S3_BUCKET_NAME")
        model_id = body.get("model_id")
        embedding_model_id = body.get("embedding_model_id")
        approach = body.get("approach")
        database_type = body.get("database_type")
        db_conn_conf = body.get("db_conn_conf")
        metadata = body.get("metadata")
        table_selection = body.get("table_selection")
        db_schema_file = None
        model_args = body.get("model_args")
        question = body.get("question")
        session = body.get("session")
        logger.info(f"Processing question: {question}")
        logger.info(f"Using model: {model_id}, approach: {approach}")

        print("Get schema file")
        if database_type == 's3':
            file_key = db_conn_conf.get("database") + "/schema/data_analyst_" + db_conn_conf.get("database") + "_schema.txt"
            schema_file = s3_key_exists(S3_BUCKET, file_key)
            if schema_file:
                db_schema_file = file_key
                print(f"Existed schema file: {db_schema_file}")
            else:
                db_schema_file = None
                print(f"Schema file not existed: {db_schema_file}")
        else:
            if session == "new":
                db_schema_file = None
            elif session == "existing":
                file_key = "schema/" + db_conn_conf.get("database") + "_schema.txt"
                schema_file = s3_key_exists(S3_BUCKET, file_key)
                if schema_file:
                    db_schema_file = file_key
                else:
                    schema_file = None

        # Initialize SQL generator
        try:
            st = time.time()
            sql_generator = SQLGeneratorBedrock(
                model_id,
                approach,
                database_type,
                db_conn_conf,
                db_schema_file,
                table_selection,
                LLM_CONF[model_id],
            )
            end = time.time()
            logger.info(f"Creating SQLGeneratorBedrock response time: {end-st}")
        except KeyError as e:
            log_error(f"Invalid model_id: {model_id}", e)
            raise ValueError(f"Invalid model_id: {model_id}. Error: {str(e)}")
        except Exception as e:
            log_error(f"Failed to initialize SQL generator:", e)
            raise SQLGenerationError(f"Failed to initialize SQL generator: {str(e)}")

        try:
            st = time.time()
            generator_function = (
                sql_generator.generate_zeroshot
                if approach == "zero_shot"
                else sql_generator.generate_fewshot
            )

            if database_type == 's3':
                table_meta = db_conn_conf.get("database") + "/metadata/" + db_conn_conf.get("database") + "_tables.xlsx"
                colum_meta = db_conn_conf.get("database") + "/metadata/" + db_conn_conf.get("database") + "_columns.xlsx"
                metric_meta = db_conn_conf.get("database") + "/metadata/" + db_conn_conf.get("database") + "_metrics.xlsx"
                sql, schema_info, foreign_key_str, schema_meta = generator_function(
                    question,
                    database_type,
                    table_meta=table_meta,
                    column_meta=colum_meta,
                    metric_meta=metric_meta,
                    table_access=None,
                    is_meta=metadata["is_meta"],
                    s3_bucket_name=S3_BUCKET,
                    embedding_model_id=embedding_model_id
                )
            else:
                sql, schema_info, foreign_key_str, schema_meta = generator_function(
                    question,
                    table_meta=metadata["table_meta"],
                    column_meta=metadata["column_meta"],
                    metric_meta=metadata["metric_meta"],
                    table_access=metadata["table_access"],
                    is_meta=metadata["is_meta"],
                    s3_bucket_name=metadata["s3_bucket_name"],
                    embedding_model_id=embedding_model_id
                )
            logger.info(f"Generated SQL: {sql}")

            try:
                if session == "new" and database_type != 's3':
                    s3_key = (
                        "schema/" + db_conn_conf.get("database") + "_schema" + ".txt"
                    )
                    s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=schema_meta)
                end = time.time()
                logger.info(f"transferring to S3 response time: {end-st}")
            except Exception as e:
                log_error(f"Failed to upload schema:", e)
                raise SQLGenerationError(f"Failed to upload schema: {str(e)}")
        except Exception as e:
            log_error(f"Failed to generate SQL:", e)
            raise SQLGenerationError(f"Failed to generate SQL: {str(e)}")

        # Execute SQL
        try:
            st = time.time()
            db_helper = sql_generator._db_helper
            #if not cached_flag:
            logger.info("Executing SQL")
            res, sql = db_helper.run_sql(question, sql, schema_meta)
            if isinstance(res, pd.DataFrame):
                result_dict = res.to_dict(orient="records")
                error = ""
            elif isinstance(res, str):
                result_dict = []
                error = "error"
            else:
                result_dict = []
                error = ""
            end = time.time()
            logger.info(f"Execution SQL response time: {end-st}")
        except Exception as e:
            log_error(f"Database operation failed:", e)
            raise DatabaseError(f"Database operation failed: {str(e)}")
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(
                {"sql_query": sql, "result": result_dict, "error": error},
                default=str
            ),
        }

    except (ValueError, SQLGenerationError) as e:
        return format_error_response(e, 400)

    except DatabaseError as e:
        return format_error_response(e, 503)

    except Exception as e:
        return format_error_response(e, 500)


def handle_timeout(func):
    """Decorator to handle Lambda timeout"""

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error("Lambda execution timed out")
            return format_error_response(
                Exception("Request timed out. Please try again."), 504
            )

    return wrapper


# Apply timeout handler
lambda_handler = handle_timeout(lambda_handler)
