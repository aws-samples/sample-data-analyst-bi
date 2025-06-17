import time
import logging
import sqlite3
import psycopg2
import boto3
from abc import ABC, abstractmethod
import pandas as pd
import json
import os
import io
import re
from decimal import Decimal

from scripts.sql.rectifier import Rectifier
from scripts.utils import s3

logger = logging.getLogger(__name__)


class DatabaseHelper(ABC):
    supported_databases = ["sqlite", "postgresql", "redshift", "s3"]

    def __init__(
        self,
        database: str,
        db_conn_conf: dict[str, str],
        schema: str,
        llm_id: str,
        llm_params: dict,
        rectification_attempt: int,
    ) -> None:
        super().__init__()
        if database not in self.supported_databases:
            raise ValueError(
                f"Error: {database} not in supported databases {self.supported_databases}"
            )
        self.database = database
        self.db_conn_conf = db_conn_conf
        self.schema = schema
        self.llm_id = llm_id
        self.llm_params = llm_params
        self.rectification_attempt = rectification_attempt

    def proceed_with_sql(self, sql):
        if sql.strip().upper().startswith("SELECT") or sql.strip().upper().startswith("WITH"):
            return True
        else:
            return False

    def get_schema_info_default(self, schema_file: str) -> str:
        response = s3.get_object(
            Bucket=os.environ.get("S3_BUCKET_NAME"), Key=schema_file
        )
        schema = response["Body"].read().decode("utf-8").strip()
        return schema, None, None

    @abstractmethod
    def _excute(self, command: str) -> pd.DataFrame:
        pass

    @abstractmethod
    def close_conn(self) -> None:
        pass


class SQLiteHelper(DatabaseHelper):
    def __init__(
        self,
        database: str,
        db_conn_conf: dict[str, str],
        schema: str,
        llm_id: str,
        llm_params: dict,
        rectification_attempt: int = 1,
        schema_file: str = None,
    ):
        super().__init__(
            database, db_conn_conf, schema, llm_id, llm_params, rectification_attempt
        )
        if "db_file_path" not in db_conn_conf.keys():
            raise ValueError(
                "Error: 'db_file_path' is required to load SQLite database!"
            )
        db_file = db_conn_conf["db_file_path"]
        self.schema_file = schema_file
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        try:
            self.cursor = self.conn.cursor()
        except Exception as e:
            self.conn.close()
            raise e
        try:
            self.sql_rectifier = Rectifier(llm_id, llm_params)
        except Exception as e:
            logger.info(e)
            self.rectification_attempt = 0

    def get_schema_info(self, include_fkeys=False) -> str:
        if self.schema_file is not None and len(self.schema_file.strip()) > 0:
            return self.get_schema_info_default(self.schema_file)
        else:
            self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            table_names = [row[0] for row in self.cursor.fetchall()]

            table_details = []
            foreign_key_relations = []

            for table_name in table_names:
                # Get column information
                self.cursor.execute(f"PRAGMA table_info({table_name})")
                columns = self.cursor.fetchall()

                # Get foreign key information
                self.cursor.execute(f"PRAGMA foreign_key_list({table_name})")
                foreign_key_list = self.cursor.fetchall()

                # Create a set of foreign key column names for this table
                foreign_key_columns = set(fk[3] for fk in foreign_key_list)

                for column in columns:
                    column_name = column[1]
                    data_type = column[2]

                    if column[5] == 1:  # Primary Key
                        key_type = "Primary Key"
                    elif column_name in foreign_key_columns:  # Foreign Key
                        key_type = "Foreign Key"
                    else:
                        key_type = "None"

                    table_details.append(
                        {
                            "table_name": table_name,
                            "column_name": column_name,
                            "data_type": data_type,
                            "key_type": key_type,
                        }
                    )

                # Add foreign key relationships
                for fk in foreign_key_list:
                    foreign_key_relations.append(
                        f"{table_name} : {fk[3]} equals {fk[2]} : {fk[4]}"
                    )

            schema_df = pd.DataFrame(table_details)
            foreign_key_str = " | ".join(foreign_key_relations)

            return schema_df, foreign_key_str, None

    def _excute(self, command):
        if self.proceed_with_sql(command):
            try:
                result = pd.read_sql(command, self.conn)
            except Exception as e:
                logger.info(e)
                result = f"{e}"
        else:
            result = "Error: Generated SQL not valid! Please retry with a different question."

        return result

    def run_sql(self, question: str, command: str) -> tuple[pd.DataFrame | str, str]:
        result = self._excute(command)
        logger.info(f"first result: {result}")
        if self.rectification_attempt > 0:
            rectification_cnt = 0
            while (
                isinstance(result, str)
                and rectification_cnt < self.rectification_attempt
            ):
                rectification_cnt += 1
                command = self.sql_rectifier.correct(
                    self.database, question, command, result
                )
                result = self._excute(command)
                logger.info(
                    f"rectification count: {rectification_cnt}, sql: {command}, result: {result}"
                )

        return result, command

    def close_conn(self):
        self.conn.close()


class PostgreSQLHelper(DatabaseHelper):
    def __init__(
        self,
        database: str,
        db_conn_conf: dict[str, str],
        schema: str,
        llm_id: str,
        llm_params: dict,
        rectification_attempt: int = 1,
        schema_file: str = None,
    ):
        super().__init__(
            database, db_conn_conf, schema, llm_id, llm_params, rectification_attempt
        )
        self.schema_file = schema_file
        self.conn = psycopg2.connect(
            database=db_conn_conf["database"],
            user=db_conn_conf["user"],
            password=db_conn_conf["password"],
            host=db_conn_conf["host"],
            port=db_conn_conf["port"],
        )
        try:
            self.conn.autocommit = True
            self.cursor = self.conn.cursor()
        except Exception as e:
            logger.info('PostgreSQLHelper connection error: %s', e)
            self.conn.close()
        try:
            self.sql_rectifier = Rectifier(llm_id, llm_params)
        except Exception as e:
            logger.info('PostgreSQLHelper rectifier initialization error: %s', e)
            self.rectification_attempt = 0

    def get_schema_info(self, table_name="income", include_fkeys=False, max_values_per_column=20):
        """Extract schema details along with distinct values (up to a max per column) using psycopg2."""
        print("table_name inside get_schema_info", table_name)
        if self.schema_file is not None and len(self.schema_file.strip()) > 0:
            return self.get_schema_info_default(self.schema_file)
        
        try:
            # Query to extract schema information
            self.cursor.execute("""
                SELECT
                    c.table_name,
                    c.column_name,
                    c.data_type,
                    c.is_nullable,
                    COALESCE(tc.constraint_types, 'None') AS constraints,
                    COALESCE(fk.foreign_key, '') AS foreign_key
                FROM
                    information_schema.columns c
                LEFT JOIN (
                    SELECT
                        ccu.table_name,
                        ccu.column_name,
                        STRING_AGG(DISTINCT tc.constraint_type, ', ') AS constraint_types
                    FROM
                        information_schema.table_constraints tc
                    JOIN
                        information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
                    WHERE
                        tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE', 'NOT NULL', 'CHECK')
                    GROUP BY
                        ccu.table_name, ccu.column_name
                ) tc ON c.table_name = tc.table_name AND c.column_name = tc.column_name
                LEFT JOIN (
                    SELECT
                        kcu.table_name,
                        kcu.column_name,
                        CONCAT(kcu.table_name, ' : ', kcu.column_name, ' equals ', ccu.table_name, ' : ', ccu.column_name) AS foreign_key
                    FROM
                        information_schema.table_constraints tc
                    JOIN
                        information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
                    JOIN
                        information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
                    WHERE
                        tc.constraint_type = 'FOREIGN KEY'
                ) fk ON c.table_name = fk.table_name AND c.column_name = fk.column_name
                WHERE
                    c.table_schema = 'public'
                ORDER BY
                    c.table_name, c.column_name;
            """)
            table_details = self.cursor.fetchall()
            print("table_details", table_details)

            # Convert to DataFrame
            schema_df = pd.DataFrame(
                table_details,
                columns=[
                    "table_name",
                    "column_name",
                    "data_type",
                    "is_nullable",
                    "key_type",
                    "foreign_key",
                ],
            )
            print("schema_df", schema_df)

            # Extract distinct values per column
            distinct_values = {}
            for _, row in schema_df.iterrows():
                table_name = row["table_name"]
                column_name = row["column_name"]
                
                try:
                    query = f"SELECT DISTINCT {column_name} FROM {table_name} LIMIT {max_values_per_column};"
                    self.cursor.execute(query)
                    values = [row[0] for row in self.cursor.fetchall()]
                    distinct_values[f"{table_name}.{column_name}"] = values
                except Exception as e:
                    logger.warning(f"Warning: Could not fetch distinct values for {table_name}.{column_name} - {e}")

            # Convert distinct values dictionary to a DataFrame for better readability
            distinct_df = pd.DataFrame(
                [(k, v) for k, v in distinct_values.items()], 
                columns=["column", "distinct_values"]
            )

            foreign_key_str = " | ".join(schema_df["foreign_key"].dropna().unique())

            return schema_df, foreign_key_str, distinct_df

        except psycopg2.Error as e:
            logger.error(f"Error retrieving schema information: {e}")
            return None, None, None

    def preprocess_sql(self, sql):
        possible_cases = [
            " id ",
            ".id ",
            " id,",
            ",id ",
            ".id,",
            ",id)",
            " id)",
            ".id)",
            "(id ",
            "(id,",
            "(id)",
            " id\n",
            "(id\n",
            ",id\n",
        ]
        sql = sql.lower()
        for c in possible_cases:
            if c in sql:
                sql = sql.replace(c, c.replace("id", '"id"'))
                logger.info(f"{c} replaced {sql}")
        return sql.upper()

    def _excute(self, command: str) -> pd.DataFrame:
        command = self.preprocess_sql(command)
        if self.proceed_with_sql(command):
            try:
                result = pd.read_sql(command, self.conn)
                result = result.applymap(lambda x: float(x) if isinstance(x, Decimal) else x)
            except Exception as e:
                logger.info(e)
                result = f"{e}"
        else:
            result = "Error: Generated SQL not valid! Please retry with a different question."
        return result

    def run_sql(
        self, question: str, command: str, schema_meta: str
    ) -> tuple[pd.DataFrame | str, str]:
        if command.strip().upper().startswith("SELECT ") or command.strip().upper().startswith("WITH "):
            logger.info("INSIDE IF")
        else:
            logger.info("INSIDE ELSE")
        result = self._excute(command)
        logger.info(f"SQL execution result: {result}")
        logger.info(f"Max rectification Limit: {self.rectification_attempt}")
        logger.info(f"isinstance of str: {isinstance(result, str)}")
        if self.rectification_attempt > 0:
            rectification_cnt = 0
            while (
                isinstance(result, str)
                and rectification_cnt < self.rectification_attempt
            ):
                rectification_cnt += 1
                command = self.sql_rectifier.correct(
                    self.database, question, command, result, schema_meta
                )
                result = self._excute(command)
                logger.info(
                    f"rectification count: {rectification_cnt}, sql: {command}, result: {result}"
                )
        return result, command

    def close_conn(self):
        self.conn.close()


class RedshiftHelper(DatabaseHelper):
    def __init__(
        self,
        database: str,
        db_conn_conf: dict[str, str],
        schema: str,
        llm_id: str,
        llm_params: dict,
        rectification_attempt: int = 1,
        schema_file: str = None,
    ):
        super().__init__(
            database, db_conn_conf, schema, llm_id, llm_params, rectification_attempt
        )
        self.schema_file = schema_file
        self.conn = psycopg2.connect(
            database=db_conn_conf["database"],
            user=db_conn_conf["user"],
            password=db_conn_conf["password"],
            host=db_conn_conf["host"],
            port=db_conn_conf["port"],
        )
        try:
            self.conn.autocommit = True
            self.cursor = self.conn.cursor()
        except Exception as e:
            logger.info('RedshiftHelper connection error: %s', e)
            self.conn.close()
        try:
            self.sql_rectifier = Rectifier(llm_id, llm_params)
        except Exception as e:
            logger.info('RedshiftHelper rectifier initialization error: %s', e)
            self.rectification_attempt = 0

    def get_schema_info(self, include_fkeys=False, max_values_per_column=20):
        """Extract schema details along with distinct values (up to a max per column) for Amazon Redshift."""
        
        if self.schema_file is not None and len(self.schema_file.strip()) > 0:
            return self.get_schema_info_default(self.schema_file)
        
        try:
            # Query to extract schema information from Redshift system tables
            self.cursor.execute("""
                WITH pk_constraints AS (
                    SELECT DISTINCT
                        n.nspname as schema_name,
                        TRIM(cl.relname) as table_name,
                        a.attname as column_name,
                        'PRIMARY KEY' as constraint_type
                    FROM pg_constraint c
                    JOIN pg_namespace n ON n.oid = c.connamespace
                    JOIN pg_class cl ON cl.oid = c.conrelid
                    JOIN pg_attribute a ON 
                        a.attrelid = c.conrelid 
                        AND a.attnum = ANY(c.conkey)
                    WHERE c.contype = 'p'
                ),
                fk_constraints AS (
                    SELECT DISTINCT
                        source_schema.nspname as schema_name,
                        TRIM(source_table.relname) as table_name,
                        att.attname as column_name,
                        'FOREIGN KEY' as constraint_type,
                        'REFERENCES ' || target_schema.nspname || '.' || 
                        TRIM(target_table.relname) || '(' || target_att.attname || ')' as foreign_key_def
                    FROM pg_constraint con
                    JOIN pg_namespace source_schema ON con.connamespace = source_schema.oid
                    JOIN pg_class source_table ON con.conrelid = source_table.oid
                    JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = ANY(con.conkey)
                    JOIN pg_class target_table ON con.confrelid = target_table.oid
                    JOIN pg_namespace target_schema ON target_table.relnamespace = target_schema.oid
                    JOIN pg_attribute target_att ON target_att.attrelid = con.confrelid AND target_att.attnum = ANY(con.confkey)
                    WHERE con.contype = 'f'
                ),
                all_constraints AS (
                    SELECT 
                        schema_name,
                        table_name,
                        column_name,
                        constraint_type,
                        NULL as foreign_key_def
                    FROM pk_constraints
                    UNION ALL
                    SELECT 
                        schema_name,
                        table_name,
                        column_name,
                        constraint_type,
                        foreign_key_def
                    FROM fk_constraints
                )
                SELECT 
                    t.tablename as table_name,
                    t."column" as column_name,
                    t.type as data_type,
                    CASE 
                        WHEN t."notnull" = true THEN 'NO'
                        ELSE 'YES'
                    END as is_nullable,
                    COALESCE(ac.constraint_type, 'None') as constraints,
                    COALESCE(ac.foreign_key_def, '') as foreign_key
                FROM pg_table_def t
                LEFT JOIN all_constraints ac ON 
                    t.schemaname = ac.schema_name
                    AND t.tablename = ac.table_name 
                    AND t."column" = ac.column_name
                WHERE t.schemaname = 'public'
                ORDER BY 
                    t.tablename,
                    t."column";
            """)
            table_details = self.cursor.fetchall()

            # Convert to DataFrame
            schema_df = pd.DataFrame(
                table_details,
                columns=[
                    "table_name",
                    "column_name",
                    "data_type",
                    "is_nullable",
                    "key_type",
                    "foreign_key",
                ],
            )

            # Extract distinct values per column
            distinct_values = {}
            for _, row in schema_df.iterrows():
                table_name = row["table_name"]
                column_name = row["column_name"]
                
                try:
                    query = f"SELECT DISTINCT {column_name} FROM {table_name} LIMIT {max_values_per_column};"
                    self.cursor.execute(query)
                    values = [row[0] for row in self.cursor.fetchall()]
                    distinct_values[f"{table_name}.{column_name}"] = values
                except Exception as e:
                    logger.warning(f"Warning: Could not fetch distinct values for {table_name}.{column_name} - {e}")

            # Convert distinct values dictionary to a DataFrame for better readability
            distinct_df = pd.DataFrame(
                [(k, v) for k, v in distinct_values.items()], 
                columns=["column", "distinct_values"]
            )

            foreign_key_str = " | ".join(schema_df["foreign_key"].dropna().unique())

            return schema_df, foreign_key_str, distinct_df

        except Exception as e:
            logger.error(f"Error retrieving schema information: {e}")
            return None

    def preprocess_sql(self, sql):
        possible_cases = [
            " id ",
            ".id ",
            " id,",
            ",id ",
            ".id,",
            ",id)",
            " id)",
            ".id)",
            "(id ",
            "(id,",
            "(id)",
            " id\n",
            "(id\n",
            ",id\n",
        ]
        sql = sql.lower()
        for c in possible_cases:
            if c in sql:
                sql = sql.replace(c, c.replace("id", '"id"'))
                logger.info(f"{c} replaced {sql}")
        return sql.upper()

    def _excute(self, command: str) -> pd.DataFrame:
        command = self.preprocess_sql(command)
        if self.proceed_with_sql(command):
            try:
                # Using cursor.execute() instead of pd.read_sql for better Redshift compatibility
                # result = pd.read_sql(command, self.conn)
                # result = result.applymap(lambda x: float(x) if isinstance(x, Decimal) else x)
                self.cursor.execute(command)
                columns = [desc[0] for desc in self.cursor.description]
                result = pd.DataFrame(self.cursor.fetchall(), columns=columns)
                result = result.applymap(lambda x: float(x) if isinstance(x, Decimal) else x)
            except Exception as e:
                logger.info(e)
                result = f"{e}"
        else:
            result = "Error: Generated SQL not valid! Please retry with a different question."
        return result

    def run_sql(
        self, question: str, command: str, schema_meta: str
    ) -> tuple[pd.DataFrame | str, str]:
        if command.strip().upper().startswith("SELECT ") or command.strip().upper().startswith("WITH "):
            logger.info("INSIDE IF")
        else:
            logger.info("INSIDE ELSE")
        result = self._excute(command)
        logger.info(f"SQL execution result: {result}")
        logger.info(f"Max rectification Limit: {self.rectification_attempt}")
        logger.info(f"isinstance of str: {isinstance(result, str)}")
        if self.rectification_attempt > 0:
            rectification_cnt = 0
            while (
                isinstance(result, str)
                and rectification_cnt < self.rectification_attempt
            ):
                rectification_cnt += 1
                command = self.sql_rectifier.correct(
                    self.database, question, command, result, schema_meta
                )
                result = self._excute(command)
                logger.info(
                    f"rectification count: {rectification_cnt}, sql: {command}, result: {result}"
                )
        return result, command

    def close_conn(self):
        self.conn.close()

class S3AthenaHelper(DatabaseHelper):
    def __init__(
        self,
        database: str,
        db_conn_conf: dict[str, str],
        schema: str,
        llm_id: str,
        llm_params: dict,
        rectification_attempt: int = 1,
        schema_file: str = None,
    ):
        super().__init__(
            database, db_conn_conf, schema, llm_id, llm_params, rectification_attempt
        )
        if schema_file:
            self.schema_file = schema_file
        else:
            self.schema_file = db_conn_conf.get("database") + "/schema/data_analyst_" + db_conn_conf.get("database") + "_schema.txt"
        
        # Initialize Athena client
        logger.info("Initializing Athena client")
        self.athena_client = boto3.client('athena')
        logger.info("Athena client initialized!")

        # Set up S3 paths
        self.s3_client = boto3.client('s3')
        self.bucket_name = os.environ.get('S3_BUCKET_NAME')
        self.db_name = db_conn_conf.get("database")
        folder_key = f"{self.db_name}/athena-output/"
        
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=folder_key)
            logger.info("S3 athena-output folder exists!")
        except:
            self.s3_client.put_object(Bucket=self.bucket_name, Key=folder_key)
            logger.info("S3 athena-output folder created!")
        
        self.s3_output = f"s3://{self.bucket_name}/{self.db_name}/athena-output"
        
        # Create Athena tables if they don't exist
        self.create_athena_tables()

        try:
            self.sql_rectifier = Rectifier(llm_id, llm_params)
        except Exception as e:
            logger.info('S3AthenaHelper rectifier initialization error: %s', e)
            self.rectification_attempt = 0
            
    def get_schema_info(self, include_fkeys=False, max_values_per_column=20):        
        if self.schema_file is not None and len(self.schema_file.strip()) > 0:
            try:
                return self.get_schema_info_default(self.schema_file)
            except Exception as e:
                logger.info('S3AthenaHelper: Failed to get schema info file from S3: %s', e)
                return None
        else:
            raise Exception(f"No schema info file found in S3!")

    def create_athena_tables(self):
        """Create Athena tables based on schema info JSON file"""
        try:
            # First, create the database if it doesn't exist
            create_db_query = f"CREATE DATABASE IF NOT EXISTS {self.db_name}"
            self._execute_athena_query_direct(create_db_query)
            logger.info(f"Created or verified database: {self.db_name}")
            
            # Read the schema info JSON file
            schema_info_path = f"{self.db_name}/schema/data_analyst_{self.db_name}_schema_info.json"
            logger.info(f"Reading schema info from: {schema_info_path}")
            
            try:
                # Get schema info from S3
                response = self.s3_client.get_object(Bucket=self.bucket_name, Key=schema_info_path)
                schema_info = json.loads(response['Body'].read().decode('utf-8'))
                
                # Create each table from schema info
                for table_name, table_info in schema_info.items():
                    columns = []
                    
                    # Process column information from data_types field
                    for data_type in table_info['data_types']:
                        for column_name, col_type in data_type.items():
                            # Map to Athena data types
                            if 'INT' in col_type.upper():
                                athena_type = 'BIGINT'
                            elif 'FLOAT' in col_type.upper() or 'DOUBLE' in col_type.upper() or 'DECIMAL' in col_type.upper() or 'NUMERIC' in col_type.upper():
                                athena_type = 'DOUBLE'
                            elif 'DATE' in col_type.upper() or 'TIME' in col_type.upper():
                                athena_type = 'TIMESTAMP'
                            elif 'BOOL' in col_type.upper():
                                athena_type = 'BOOLEAN'
                            else:
                                athena_type = 'STRING'
                            columns.append(f"`{column_name}` {athena_type}")   

                    if columns:
                        # Create table query
                        create_table_query = f"""
                        CREATE EXTERNAL TABLE IF NOT EXISTS `{table_name}` (
                            {', '.join(columns)}
                        )
                        ROW FORMAT DELIMITED
                        FIELDS TERMINATED BY ','
                        STORED AS TEXTFILE
                        LOCATION 's3://{self.bucket_name}/{self.db_name}/data/{self.db_name}/{table_name}/'
                        TBLPROPERTIES ('skip.header.line.count'='1')
                        """
                        
                        self._execute_athena_query_direct(create_table_query)
                        logger.info(f"Created or verified table: {table_name}")
                    else:
                        logger.info(f"No columns found for table: {table_name}")
                        
            except Exception as e:
                logger.error(f"Error reading schema info or creating tables: {e}")
                raise Exception(f"Failed to create athena tables: {e}")
                
        except Exception as e:
            logger.error(f"Error creating Athena database: {e}")
    
    def _execute_athena_query_direct(self, query):
        """Execute an Athena query directly without returning results"""
        try:
            response = self.athena_client.start_query_execution(
                QueryString=query,
                QueryExecutionContext={'Database': self.db_name},
                ResultConfiguration={'OutputLocation': self.s3_output}
            )
            
            # Wait for query to complete
            query_execution_id = response['QueryExecutionId']
            while True:
                response = self.athena_client.get_query_execution(QueryExecutionId=query_execution_id)
                state = response['QueryExecution']['Status']['State']
                if state in ['SUCCEEDED', 'FAILED', 'CANCELLED']:
                    break
                time.sleep(1)
                
            if state != 'SUCCEEDED':
                error_reason = response['QueryExecution']['Status'].get('StateChangeReason', 'Unknown error')
                logger.info(f"Query failed: {error_reason}")
                
            return query_execution_id
        except Exception as e:
            logger.error(f"Error executing Athena query: {e}")
            raise e
    
    def execute_athena_query(self, query):
        """Execute an Athena query and return the execution ID"""
        try:
            response = self.athena_client.start_query_execution(
                QueryString=query,
                QueryExecutionContext={'Database': self.db_name},
                ResultConfiguration={'OutputLocation': self.s3_output}
            )
            return response['QueryExecutionId']
        except Exception as e:
            logger.error(f"Error executing Athena query: {e}")
            raise e

    def check_query_status(self, execution_id):
        """Check the status of an Athena query"""
        response = self.athena_client.get_query_execution(QueryExecutionId=execution_id)
        return response['QueryExecution']['Status']['State']

    def get_query_results(self, execution_id):
        """Wait for query completion and get results"""
        while True:
            status = self.check_query_status(execution_id)
            if status in ['SUCCEEDED', 'FAILED', 'CANCELLED']:
                break
            time.sleep(1)  # Polling interval

        if status == 'SUCCEEDED':
            return self.athena_client.get_query_results(QueryExecutionId=execution_id)
        else:
            error_info = self.athena_client.get_query_execution(QueryExecutionId=execution_id)
            error_reason = error_info['QueryExecution']['Status'].get('StateChangeReason', 'Unknown error')
            raise Exception(f"Query failed with status '{status}': {error_reason}")

    def _excute(self, command: str) -> pd.DataFrame:
        if self.proceed_with_sql(command):
            try:
                # Execute query using Athena with improved error handling
                execution_id = self.execute_athena_query(command)
                results = self.get_query_results(execution_id)
                
                # Convert results to DataFrame
                columns = [col['Label'] for col in results['ResultSet']['ResultSetMetadata']['ColumnInfo']]
                data = []
                for row in results['ResultSet']['Rows'][1:]:  # Skip header row
                    data.append([col.get('VarCharValue', '') for col in row['Data']])
                    
                result = pd.DataFrame(data, columns=columns)
                
                # Convert numeric columns
                for col in result.columns:
                    try:
                        result[col] = pd.to_numeric(result[col])
                    except:
                        pass
                        
            except Exception as e:
                logger.error(f"Athena query execution error: {e}")
                result = f"{e}"
        else:
            result = "Error: Generated SQL not valid! Please retry with a different question."
            
        return result

    def run_sql(
        self, question: str, command: str, schema_meta: str
    ) -> tuple[pd.DataFrame | str, str]:
        if command.strip().upper().startswith("SELECT ") or command.strip().upper().startswith("WITH "):
            logger.info("INSIDE IF")
        else:
            logger.info("INSIDE ELSE")
        result = self._excute(command)
        logger.info(f"SQL execution result: {result}")
        logger.info(f"Max rectification Limit: {self.rectification_attempt}")
        logger.info(f"isinstance of str: {isinstance(result, str)}")
        
        # Check for TABLE_NOT_FOUND error and recreate database if needed
        if isinstance(result, str) and "TABLE_NOT_FOUND" in result:
            logger.info(f"TABLE_NOT_FOUND error detected. Dropping and recreating database {self.db_name}")
            try:
                # Drop the database
                drop_db_query = f"DROP DATABASE IF EXISTS {self.db_name} CASCADE"
                self._execute_athena_query_direct(drop_db_query)
                logger.info(f"Database {self.db_name} dropped successfully")
                
                # Recreate tables
                self.create_athena_tables()
                
                # Retry the query
                result = self._excute(command)
            except Exception as e:
                logger.error(f"Error recreating database: {e}")
        
        if self.rectification_attempt > 0:
            rectification_cnt = 0
            while (
                isinstance(result, str)
                and rectification_cnt < self.rectification_attempt
            ):
                rectification_cnt += 1
                command = self.sql_rectifier.correct(
                    self.database, question, command, result, schema_meta
                )
                result = self._excute(command)
                logger.info(
                    f"rectification count: {rectification_cnt}, sql: {command}, result: {result}"
                )
                
        return result, command
    
    def close_conn(self) -> None:
        pass

def get_database_helper(
    database: str,
    db_conn_conf: dict[str, str],
    schema: str,
    llm_id: str,
    llm_params: dict,
    rectification_attempt: int = 1,
    schema_file: str = None,
) -> DatabaseHelper:
    database = database.strip().lower()
    if database == "sqlite":
        return SQLiteHelper(
            database,
            db_conn_conf,
            schema,
            llm_id,
            llm_params,
            rectification_attempt,
            schema_file,
        )
    elif database == "postgresql":
        return PostgreSQLHelper(
            database,
            db_conn_conf,
            schema,
            llm_id,
            llm_params,
            rectification_attempt,
            schema_file,
        )
    elif database == "redshift":
        return RedshiftHelper(
            database,
            db_conn_conf,
            schema,
            llm_id,
            llm_params,
            rectification_attempt,
            schema_file,
        )
    elif database == "s3":
        return S3AthenaHelper(
            database,
            db_conn_conf,
            schema,
            llm_id,
            llm_params,
            rectification_attempt,
            schema_file,
        )
    else:
        raise ValueError(
            f"Error: {database} not in supported databases {DatabaseHelper.supported_databases}"
        )