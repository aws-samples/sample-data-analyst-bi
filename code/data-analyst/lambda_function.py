import json
import boto3
import base64
import logging
import os
import io
from typing import Dict, Any, Tuple
from scripts.orchestrator_db import question_intent, generate_answers_db, generate_plots, generate_answer_en
from scripts.query_db.get_schema_str import DatabaseSchemaExtractor
from scripts.query_db.sql_config import ACTIVE_DB_CONFIG
from scripts.query_db.prompt_config_clv3 import intent_prompt
from scripts.time_tracker import ProcessingTimeTracker
from scripts.cache_operations import write_to_cache, get_cached_query
from scripts.query_db.pgsql_executor import get_sql_result

# Configure logging at root level
def setup_logging():
    """Set up comprehensive logging configuration"""
    # Get log level from environment variable, default to INFO
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    
    # Convert string to logging level
    numeric_level = getattr(logging, log_level, logging.INFO)
    
    # Configure root logger
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True  # This ensures existing loggers are reconfigured
    )
    
    # Get root logger and set level
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Ensure all child loggers inherit the level
    for logger_name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        logger.setLevel(numeric_level)
    
    return root_logger

# Initialize logging
logger = setup_logging()
logger.info(f"Logging initialized at level: {logger.level}")

s3 = boto3.client('s3')

# Initialize the tracker
time_tracker = ProcessingTimeTracker()

class SQLGenerationError(Exception):
    """Custom exception for SQL generation errors"""

    pass

def api_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format the API Gateway response
    
    Args:
        status_code (int): HTTP status code
        body (dict): Response body
        
    Returns:
        dict: Formatted API Gateway response
    """
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
        #   'Access-Control-Allow-Origin': '*'  # Adjust this for your CORS needs
        },
        'body': json.dumps(body)
    }



def initialize_schema_extractor(db_config: dict, metadata:dict) -> Tuple[dict, str, DatabaseSchemaExtractor]:
    """
    Initialize database schema extractor and get schema string
    
    Args:
        db_config (dict): Database configuration parameters
        
    Returns:
        tuple: (schema_string, extractor_instance)
            - schema_string (str): Extracted schema as string, empty if error occurred
            - extractor_instance (DatabaseSchemaExtractor): Initialized extractor instance
    """
    schema_str = ""
    schema_info = {}
    
    logger.info(f"=== SCHEMA EXTRACTION DEBUG START ===")
    logger.info(f"Database config received: {db_config}")
    logger.info(f"Metadata received: {metadata}")
    
    # Initialize extractor
    try:
        extractor = DatabaseSchemaExtractor(db_config['db_type'])
        logger.info(f"Extractor initialized successfully for type: {db_config['db_type']}")
    except Exception as e:
        logger.error(f"Failed to initialize extractor: {e}")
        return {}, "", None
    
    # Establish connection with timeout handling
    try:
        connection_params = {k: v for k, v in db_config.items() if k != 'db_type'}
        logger.info(f"Attempting to connect with params: {connection_params}")
        
        # Additional debug for S3 connections
        if db_config['db_type'] == 's3':
            logger.info(f"S3 bucket from env: {os.environ.get('S3_BUCKET_NAME')}")
            logger.info(f"Database prefix: {connection_params.get('database')}")
        
        extractor.connect(**connection_params)
        logger.info("Connected successfully")
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        logger.error(f"Connection error type: {type(e).__name__}")
        logger.error(f"Connection error details: {str(e)}")
        
        return {}, "", extractor
        
    # Extract schema with timeout handling
    try:
        logger.info("Starting schema extraction...")
        logger.info(f"Calling extract_schema with metadata: {metadata}")
        
        extractor.extract_schema(metadata)
        logger.info("Schema extraction completed")
        
        # Check if schema_info was populated
        logger.info(f"Schema info keys: {list(extractor.schema_info.keys()) if hasattr(extractor, 'schema_info') else 'No schema_info attribute'}")
        logger.info(f"Number of tables found: {len(extractor.schema_info) if hasattr(extractor, 'schema_info') else 0}")
        
        if hasattr(extractor, 'schema_info') and extractor.schema_info:
            for table_name, table_info in extractor.schema_info.items():
                logger.info(f"Table {table_name}: {len(table_info.get('columns', []))} columns")
        else:
            logger.warning("Schema info is empty or missing after extraction")
            
    except Exception as e:
        logger.error(f"Schema extraction failed: {e}")
        logger.error(f"Schema extraction error type: {type(e).__name__}")
        logger.error(f"Schema extraction error details: {str(e)}")
        
        # Import traceback for full error context
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        
        # Check if it's a timeout error and provide specific guidance
        if "timeout" in str(e).lower() or "connection" in str(e).lower():
            logger.error("TIMEOUT ERROR DETECTED:")
            logger.error("This usually indicates VPC networking issues:")
            logger.error("1. Lambda may be in wrong subnets (should be private with egress)")
            logger.error("2. Security groups may be blocking outbound traffic")
            logger.error("3. VPC route tables may not be configured for internet access")
            logger.error("4. NAT Gateway may not be working properly")
        
        return {}, "", extractor
        
    # Get schema string
    try:
        logger.info("Getting schema string...")
        schema_str = extractor.get_schema_string()
        logger.info(f"Schema string length: {len(schema_str)}")
        logger.info(f"Schema string preview (first 200 chars): {schema_str[:200]}...")
        
        if len(schema_str) <= 20:  # "Database Schema:" is about 16 chars
            logger.warning("Schema string is suspiciously short - likely extraction failed")
            logger.warning(f"Complete schema string: '{schema_str}'")
            
    except Exception as e:
        logger.error(f"Failed to get schema string: {e}")
        logger.error(f"Schema string error type: {type(e).__name__}")
        return {}, "", extractor
    
    # Get schema_info
    try:
        logger.info("Getting schema info...")
        schema_info = extractor.get_schema_info()
        logger.info(f"Schema info type: {type(schema_info)}")
        logger.info(f"Schema info keys: {list(schema_info.keys()) if schema_info else 'Empty'}")
    except Exception as e:
        logger.error(f"Failed to get schema info: {e}")
        logger.error(f"Schema info error type: {type(e).__name__}")
        return {}, "", extractor
    
    logger.info(f"=== SCHEMA EXTRACTION DEBUG END ===")
    logger.info(f"Returning: schema_info={bool(schema_info)}, schema_str_len={len(schema_str)}, extractor={bool(extractor)}")
    
    return schema_info, schema_str, extractor


def validate_input(event: Dict) -> tuple[Dict, str]:
    """
    Validate and extract input parameters from API Gateway event
    
    Args:
        event (dict): API Gateway event
        
    Returns:
        tuple: (parsed_body, error_message)
    """
    try:
        # Check if body exists
        if 'body'  in event:
            try:
                body = json.loads(event['body'])
            except json.JSONDecodeError:
                return None, "Invalid JSON in request body"
        else:
            body = event
                
        # Validate required fields
        required_fields = ['user_persona', 'user_query']
        missing_fields = [field for field in required_fields if field not in body]
        if missing_fields:
            return None, f"Missing required fields: {', '.join(missing_fields)}"
            
        # Validate field types
        if not isinstance(body['user_persona'], str):
            return None, "user_persona must be a string"
        if not isinstance(body['user_query'], str):
            return None, "user_query must be a string"
            
        # Create messages list if not provided
        if 'messages' not in body:
            body['messages'] = [{'role': 'user', 'content': body['user_query']}]
        elif not isinstance(body['messages'], list):
            return None, "messages must be a list"
            
        return body, ""
        
    except Exception as e:
        return None, f"Error validating input: {str(e)}"

def encode_plot(fig) -> str:
    """
    Encode plot figure to base64 string
    
    Args:
        fig: Plot figure object
        
    Returns:
        str: Base64 encoded plot
    """
    try:
        buf = io.BytesIO()
        # fig.savefig(buf, format='png')
        fig.savefig(buf, format='png', bbox_inches='tight')  # added bbox_inches='tight' for better formatting
        buf.seek(0)
        plot_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        buf.close()
        return plot_base64
    except Exception as e:
        raise Exception(f"Error encoding plot: {str(e)}")

def lambda_handler(event: Dict, context: Any) -> Dict:
    """
    Lambda handler for processing queries and generating responses
    
    Args:
        event (dict): API Gateway event
        context: Lambda context
        
    Returns:
        dict: API Gateway response
    """
    logger.debug("Received event: %s", event)
    try:
        iteration_id = event.get('user_query', context.aws_request_id)
        logger.info("Starting lambda execution with iteration_id: %s", iteration_id)
        time_tracker.start_process(iteration_id, "Validating Input")
        # Validate and extract input
        parsed_input, error_msg = validate_input(event)
        logger.debug("Parsed input: %s", parsed_input)
        time_tracker.end_process(iteration_id)
        if error_msg:
            logger.error("Input validation failed: %s", error_msg)
            time_tracker.save_times(iteration_id)
            return api_response(400, {'error': error_msg})
        
        user_persona = parsed_input['user_persona']
        user_query = parsed_input['user_query']
        query_type = parsed_input["query_type"]
        cache_thresh = parsed_input["cache_thresh"]
        question_query_map = parsed_input["question_query_map"]
        messages = parsed_input['messages']
        db_conn_conf = parsed_input.get("db_conn_conf")
        # Get vector database parameters from environment variables (deployed database)
        vector_db_params = {
            "host": os.environ.get("POSTGRES_ENDPOINT"),
            "port": int(os.environ.get("POSTGRES_PORT", 5432)),
            "database": os.environ.get("POSTGRES_DB"),
            "user": os.environ.get("POSTGRES_USERNAME"),
            "password": os.environ.get("POSTGRES_PASSWORD")
        }
        chat_model_id =  parsed_input.get("chat_model_id")
        sql_model_id =  parsed_input.get("sql_model_id")
        plot_model_id = parsed_input.get("plot_model_id")
        embedding_model_id = parsed_input.get("embedding_model_id")
        expl_model_id = parsed_input.get("expl_model_id")
        approach =  parsed_input.get("approach")
        
        # Extract region information from environment variables
        model_region = os.environ.get("SQL_MODEL_REGION", "us-east-1")
        # chat_model_region = os.environ.get("CHAT_MODEL_REGION", "us-east-1")
        # embedding_model_region = os.environ.get("EMBEDDING_MODEL_REGION", "us-east-1")
        table_selection = parsed_input.get("table_selection")
        metadata = parsed_input.get("metadata")
        session = parsed_input.get("session")
        q_mod_prompt = parsed_input.get("q_mod_prompt")
        logger.debug("q_mod_prompt: %s", q_mod_prompt)
        logger.debug("vector_db_params configured")
        logger.debug("embedding_model_id: %s", embedding_model_id)
        logger.debug("question_query_map: %s", question_query_map)
        logger.debug("expl_model_id: %s", expl_model_id)
        
        logger.info("Processing request with query_type: %s, cache_thresh: %s", query_type, cache_thresh)
        
        ## Store in cache if SQL is approved
        try:
            if question_query_map:
                logger.debug("question_query_map: %s", question_query_map)
                logger.info("Caching data")
                message, status_code = write_to_cache(expl_model_id, embedding_model_id, question_query_map, vector_db_params, expl_model_region=model_region, emb_model_region=model_region)
                response_body = {"status":"successful"}
                if status_code == 200:
                    logger.info("Entries saved to cache successfully")
                    return api_response(200, response_body)
                    logger.info("Data cached")
                else:
                    return api_response(500, {'error': "Error in caching data"})
        except Exception as e:
             logger.error("Save to Cache error: %s", e, exc_info=True)
             return api_response(500, {'error': f"Unexpected error in caching: {str(e)}"})

        ## Check cached entries
        try:
            logger.info("Cache parameters - user_query: %s, embedding_model_id: %s, cache_thresh: %s", 
                       user_query, embedding_model_id, cache_thresh)
            time_tracker.start_process(iteration_id, "get_cache_entries")
            
            logger.info("Calling get_cached_query...")
            sql = get_cached_query(
                user_query,
                embedding_model_id,
                cache_thresh,
                vector_db_params,
                embedding_model_region=model_region
            )
            logger.info("get_cached_query completed successfully")
            logger.info("cached sql result: %s", sql)
            cached_flag = True if sql else False
            logger.info("cached_flag set to: %s", cached_flag)
            time_tracker.end_process(iteration_id)
        except Exception as e:
            cached_flag = False
            logger.error("Get Cache Entries error: %s", e, exc_info=True)
            raise SQLGenerationError(f"Failed to retrieve cached SQL: {str(e)}")

        if cached_flag:
            logger.info("Cached SQL found")
            try:
                time_tracker.start_process(iteration_id, "sql_execution")
                extractor = DatabaseSchemaExtractor(db_conn_conf['db_type'])
                connection_params = {k: v for k, v in db_conn_conf.items() if k != 'db_type'}
                extractor.connect(**connection_params)
                logger.debug("Extractor initialized: %s", extractor)
                
                # Use appropriate SQL execution method based on database type
                if db_conn_conf['db_type'] == 's3':
                    # For S3, use Athena execution
                    from scripts.query_db.postprocessor import get_sql_from_athena
                    gen_text = get_sql_from_athena(sql, db_conn_conf.get("database"))
                else:
                    # For other databases, use standard SQL execution
                    gen_text = get_sql_result(sql, extractor)
                df = gen_text[0]
                error_msg = gen_text[1]
                time_tracker.end_process(iteration_id)
                if error_msg:
                    logger.error('SQL execution error: %s', error_msg)
                    return api_response(500, {'error': error_msg})
                time_tracker.start_process(iteration_id, "Explanation generation")
                if error_msg != '':
                    answer_gen = ''                    
                elif error_msg == '' and df.shape[0] == 0:
                    # answer_gen = ''
                    answer_gen = ""
                elif error_msg == '' and df.shape[0] > 0:
                    logger.debug("Messages for answer generation: %s", messages)
                    answer_gen, error_msg = generate_answer_en(chat_model_id, df, sql, messages, model_region=model_region)
                else:
                    answer_gen = ''
                time_tracker.end_process(iteration_id)
             
                response_body = {'answer': answer_gen,'sql_query': sql, 'q_cat': '', 'q_mod': '', 'mod_prompt': '' , 'filter_values': '', 'cached_flag': cached_flag}
                time_tracker.start_process(iteration_id, "Add DataFrame to SQL Response")
                if df is not None and not df.empty:
                    try:
                        # Convert dataframe to JSON string with specific formatting
                        df_json = df.to_json(orient='records', date_format='iso', double_precision=10)
                        response_body['dataframe'] = df_json
                    except Exception as e:
                        logger.error("Error serializing dataframe: %s", str(e))
                        # Optionally handle the error or continue without including the dataframe
                        response_body['dataframe'] = '[]'

                time_tracker.end_process(iteration_id)
                        
                time_tracker.save_times(iteration_id, user_query)
                return api_response(200, response_body)
            except Exception as e:
                time_tracker.save_times(iteration_id, user_query)
                return api_response(500, {'error': f"Unexpected error in cached sql execution: {str(e)}"})
            

        # Extract schema
        try:
            logger.info("Cached SQL not found, extracting schema")
            time_tracker.start_process(iteration_id, "Extract Schema")
            db_config = db_conn_conf
            logger.info("Database Type: %s", db_config['db_type'])
            # schema_str, extractor = initialize_schema_extractor(db_config)
            if db_config['db_type'] == 's3':
                schema_str_file_key = db_conn_conf.get("database") + "/schema/data_analyst_" + db_conn_conf.get("database") + "_schema.txt"
                schema_info_file_key = db_conn_conf.get("database") + "/schema/data_analyst_" + db_conn_conf.get("database") + "_schema_info.json"
            else:
                schema_str_file_key = "schema/data_analyst_" + db_conn_conf.get("database") + "_schema.txt"
                schema_info_file_key = "schema/data_analyst_" + db_conn_conf.get("database") + "_schema_info.json"

            if session == "new":
                logger.info("New Session - initializing schema extractor")
                schema_info, schema_str, extractor = initialize_schema_extractor(db_config, metadata)
            elif session == "existing":
                logger.info("Existing Session - attempting to load schema from S3")
                try:
                    # Try to load existing schema from S3
                    response = s3.get_object(Bucket = os.environ.get("S3_BUCKET_NAME"), Key=schema_str_file_key)
                    schema_str = response['Body'].read().decode('utf-8').strip()
                    logger.info("Successfully loaded schema from S3 (length: %d)", len(schema_str))
                    
                    extractor = DatabaseSchemaExtractor(db_config['db_type'])
                    try:
                        connection_params = {k: v for k, v in db_config.items() if k != 'db_type'}
                        extractor.connect(**connection_params)
                        logger.info("Connected successfully")
                        # Add this line to reinitialize schema
                        extractor.extract_schema(metadata, session, schema_info_file_key)  # Make sure metadata is available here
                    except Exception as e:
                        logger.warning("Failed to reinitialize schema, falling back to full extraction: %s", e)
                        schema_info, schema_str, extractor = initialize_schema_extractor(db_config, metadata)
                        
                except Exception as s3_error:
                    # Schema file doesn't exist in S3, treat as new session
                    logger.warning("Schema file not found in S3 (%s), treating as new session: %s", schema_str_file_key, s3_error)
                    logger.info("Falling back to new schema extraction...")
                    schema_info, schema_str, extractor = initialize_schema_extractor(db_config, metadata)
            else:
                schema_str = ""
                pass
            time_tracker.end_process(iteration_id)
            if not schema_str:
                time_tracker.save_times(iteration_id, user_query)
                return api_response(500, {'error': 'Failed to extract database schema'})
            else:
                 if session == "new":
                    s3.put_object(
                        Bucket=os.environ.get("S3_BUCKET_NAME"),
                        Key=schema_str_file_key,
                        Body=schema_str)
                    if db_config['db_type'] == 's3':
                        s3.put_object(
                            Bucket=os.environ.get("S3_BUCKET_NAME"),
                            Key=schema_info_file_key,
                            Body=json.dumps(schema_info))
            
        except Exception as e:
            time_tracker.save_times(iteration_id, user_query)
            return api_response(500, {'error': f"Error extracting schema: {str(e)}"})

        # Check question intent
        try:
            time_tracker.start_process(iteration_id, "question_intent")
            query_prompt, answer, response, formatted_query, error_msg = question_intent(chat_model_id, messages, intent_prompt, schema_str, guardrail=True, model_region=model_region)
            
            time_tracker.end_process(iteration_id)
            if error_msg:
                time_tracker.save_times(iteration_id,user_query)
                return api_response(500, {'error': error_msg})
            # If not SQL or Plot query, return response directly
            if "YesSQL" not in answer and "YesPlot" not in answer:
                time_tracker.save_times(iteration_id, user_query)
                return api_response(200, {'response': response})   
        except Exception as e:
            time_tracker.save_times(iteration_id, user_query)
            return api_response(500, {'error': f"Error in question intent: {str(e)}"})
            
        # Process SQL or Plot query
        try:
            if "YesSQL" in answer:
                # Generate SQL response
                time_tracker.start_process(iteration_id, "YesSQL")
                logger.debug("Schema string before calling lambda: %s", schema_str[:200] + "..." if len(schema_str) > 200 else schema_str)
                answer, sql_gen, error_msg, cat_gen, split_gen, prompt, df, suggestion, replacement_message = generate_answers_db(user_query, query_type, messages, extractor, schema_str, db_config, chat_model_id, sql_model_id, embedding_model_id, expl_model_id, approach, metadata, session, table_selection, q_mod_prompt, query_tabs=None, iteration_id=iteration_id, time_tracker=time_tracker, model_region=model_region) # Pass extractor

                time_tracker.end_process(iteration_id)
                
                if error_msg:
                    time_tracker.save_times(iteration_id, user_query)
                    logger.error('SQL generation error - answer: %s, error: %s', answer, error_msg)
                    return api_response(500, {'error': error_msg})
                    
                response_body = {'answer': answer,'sql_query': sql_gen, 'q_cat': cat_gen, 'q_mod': split_gen, 'mod_prompt': prompt , 'filter_values': replacement_message, 'cached_flag': cached_flag }

                # Add dataframe to response if it exists and is not empty
                time_tracker.start_process(iteration_id, "Add DataFrame to SQL Response")
                if df is not None and not df.empty:
                    try:
                        # Convert dataframe to JSON string with specific formatting
                        df_json = df.to_json(orient='records', date_format='iso', double_precision=10)
                        response_body['dataframe'] = df_json
                    except Exception as e:
                        logger.error("Error serializing dataframe: %s", str(e))
                        # Optionally handle the error or continue without including the dataframe
                        response_body['dataframe'] = '[]'

                time_tracker.end_process(iteration_id)
                logger.debug("Response body prepared: %s", {k: v if k != 'dataframe' else f"[{len(v)} chars]" for k, v in response_body.items()})
                time_tracker.save_times(iteration_id, user_query)
                return api_response(200, response_body)
                

            elif "YesPlot" in answer:
                # Generate plot
                logger.info("Invoking Generate Plot")
                time_tracker.start_process(iteration_id, "Generate Plot")
                fig, py, sql_gen, df, error_msg = generate_plots(user_query, messages, extractor, db_config, plot_model_id, sql_model_id, embedding_model_id, approach, metadata, session, query_tabs=None, model_region=model_region) # Pass Extractor instance

                time_tracker.end_process(iteration_id)

                if error_msg:
                    time_tracker.save_times(iteration_id, user_query)
                    return api_response(500, {'error': error_msg})
                    
                # Encode plot to base64
                try:
                    plot_base64 = encode_plot(fig)
                    response_body = {
                        'plot': plot_base64,
                        'python_code': py,
                        'sql_query': sql_gen,
                        'q_cat': '',
                        'q_mod': '',
                        'mod_prompt': '',
                        'filter_values': '',
                        'cached_flag': cached_flag
                        }
                    # Add dataframe to response if it exists and is not empty
                    time_tracker.start_process(iteration_id, "Add DataFrame to Plot Response")
                    if df is not None and not df.empty:
                        try:
                            # Convert dataframe to JSON string with specific formatting
                            df_json = df.to_json(orient='records', date_format='iso', double_precision=10)
                            response_body['dataframe'] = df_json

                        except Exception as e:
                            logger.error("Error serializing dataframe: %s", str(e))
                            # Optionally handle the error or continue without including the dataframe
                            response_body['dataframe'] = '[]'
                    
                    time_tracker.end_process(iteration_id)

                    time_tracker.save_times(iteration_id, user_query)
                    return api_response(200, response_body)

                    
                except Exception as e:
                    time_tracker.save_times(iteration_id, user_query)
                    return api_response(500, {'error': f"Error processing plot and data: {str(e)}"})
                               
            
        except Exception as e:
            time_tracker.save_times(iteration_id, user_query)
            return api_response(500, {'error': f"Error processing user query for SQL/Plot: {str(e)}"})
          
    except Exception as e:
        time_tracker.save_times(iteration_id, user_query)
        return api_response(500, {'error': f"Unexpected error: {str(e)}"})
