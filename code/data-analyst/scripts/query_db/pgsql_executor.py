import os
import sys
# project_root = '/home/sagemaker-user/data_analyst_bot/da_refactor'
# if project_root not in sys.path:
#     sys.path.insert(0, project_root)
import re
import pandas as pd
import datetime
import signal
import time
import logging
from sqlalchemy import text
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from scripts.query_db.config import DB_PATH,num_record_thresh, exec_time_thresh
from scripts.utils import load_data, extract_data, log_error

# Configure logging
logger = logging.getLogger(__name__)

"""
This module provides functionality for executing SQL queries with timeout and record count limitations.

The module includes a custom exception class for handling record count thresholds and functions
for executing SQL queries against PostgreSQL databases using SQLAlchemy.
"""

class NumRecordsException(Exception):
    "Raised when the number of records is more than the specified threshold"
    pass

def get_sql_result(sql, extractor):
    """Execute SQL query with timeout and row count threshold checks.

    This function executes the provided SQL query against a database with the following safety measures:
    - Enforces a maximum execution time threshold
    - Checks the result set size against a maximum row threshold
    - Handles connection errors and query execution errors
    - Uses thread pooling for timeout management

    Args:
        sql (str): The SQL query to execute
        extractor (DatabaseSchemaExtractor): Instance containing the database engine and connection details

    Returns:
        List containing:
            - pd.DataFrame: Query results as a DataFrame (empty if error occurs)
            - str: Error message if any, empty string if successful

    Raises:
        NumRecordsException: When result set exceeds configured threshold
        TimeoutError: When query execution exceeds timeout threshold
        ConnectionError: When database connection fails

    Note:
        Global configuration used:
        - num_record_thresh: Maximum number of records allowed in result
        - exec_time_thresh: Maximum execution time allowed in seconds
    """
    st_time = time.time()
    
    def execute_sql(sql, engine):
        logger.debug("Inside execute sql")
        logger.debug("engine: %s", engine)
        # logger.debug('sql in db: %s', sql)
        error_msg = ''
        try:
            # Clean the SQL query
            clean_sql = sql.replace(';', '')
            
            # Count query for PostgreSQL
            sql_cnt = text(f"SELECT COUNT(*) FROM ({clean_sql}) as subquery")
            
            with engine.connect() as connection:
                # Execute count query
                result = connection.execute(sql_cnt)
                num_rows = result.scalar()
                
                if num_record_thresh < num_rows:
                    logger.warning('num records in results more than the specified threshold')
                    df = pd.DataFrame()
                    raise NumRecordsException
                else:
                    # Execute main query
                    df = pd.read_sql_query(text(sql), connection)
                    
        except NumRecordsException as e:
            df = pd.DataFrame()
            error_msg = f"Number of data records is {num_rows} which is more than the threshold. Rephrase the question by adding a filter criteria"
        except Exception as e:
            df = pd.DataFrame()
            error_msg = str(e)
            logger.error("SQL execution error: %s", error_msg)
            log_error('DbDataRetrievalBedrock', error_msg)
        return df, error_msg
    logger.debug("extractor.engine: %s", extractor.engine)
    try:
        # Use the existing SQLAlchemy engine from the extractor
        if not extractor.engine:
            raise ConnectionError("Database connection not established")
            
        # Execute with timeout using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(execute_sql, sql, extractor.engine)
            try:
                df, error_msg = future.result(timeout=exec_time_thresh)

            except TimeoutError:
                df = pd.DataFrame()
                error_msg = "SQL execution timeout error!"
                log_error('DbDataRetrievalBedrock', error_msg)
                
    except Exception as e:
        df = pd.DataFrame()
        error_msg = f"Execution error: {str(e)}"
        logger.error("Execution error: %s", error_msg)
        log_error('DbDataRetrievalBedrock', error_msg)
    
    end_time = time.time()
    return [df, error_msg]


def get_sql_result2(sql, extractor):
    """This function is to be used to execute SQL to get the values from a column in the database.
    
    Args:
        sql (str): generated SQL query
        extractor: DatabaseSchemaExtractor instance
        
    Returns: 
        tuple: (DataFrame, error_message)
    """
    error_msg = ''
    try:
        df = pd.read_sql_query(sql, extractor.engine)  # Use engine directly, no need to create connection
    except Exception as e:
        df = pd.DataFrame()
        error_msg = str(e)
        log_error('get_sql_result2', error_msg)
    return df, error_msg
