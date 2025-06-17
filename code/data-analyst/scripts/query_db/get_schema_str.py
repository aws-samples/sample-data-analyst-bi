import os
import sys
import io
import psycopg2
import boto3
import pandas as pd
from sqlalchemy import create_engine, inspect, select, distinct
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql import text
from typing import Dict
from pandas.api.types import is_numeric_dtype, is_datetime64_any_dtype, is_string_dtype
import json
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Initialize extractor
class DatabaseSchemaExtractor:
    def __init__(self, db_type):
        self.db_type = db_type
        self.engine = None
        self.s3_client = None
        self.bucket_name = None
        self.prefix = None
        self.csv_files = []
        self.schema_info = {}

    def connect(self, **kwargs):
        """Create SQLAlchemy engine based on database type"""
        try:
            if self.db_type == 'postgresql':
                self.engine = create_engine(
                    f"postgresql://{kwargs['user']}:{kwargs['password']}@"
                    f"{kwargs['host']}:{kwargs.get('port', 5432)}/{kwargs['database']}"
                )
            elif self.db_type == 'redshift':
                self.engine = create_engine(
                    f"redshift+redshift_connector://{kwargs['user']}:{kwargs['password']}@"
                    f"{kwargs['host']}:{kwargs.get('port', 5439)}/{kwargs['database']}"
                )
            elif self.db_type == 's3':
                self.s3_client = boto3.client('s3')
                self.bucket_name = os.environ.get("S3_BUCKET_NAME")
                self.prefix = f"{kwargs.get('database')}"
                if self.bucket_name:
                    try:
                        logger.info(f"Testing connection to S3 bucket: {self.bucket_name}")
                        self.s3_client.head_bucket(Bucket=self.bucket_name)
                        logger.info(f"Testing connection to S3 bucket {self.bucket_name} succeeded!")                    
                    except Exception as e:
                        raise ConnectionError(f"S3 bucket '{self.bucket_name}' not accessible: {str(e)}")
                else:
                    raise ValueError("S3 bucket name is required")
            else:
                raise ValueError(f"Unsupported database type: {self.db_type}")
        except Exception as e:
            raise ConnectionError(f"Failed to establish connection: {str(e)}")

    def extract_schema(self, metadata, session = "new", schema_info_file_key = ""):
        """Extract schema information based on data source type"""
        logger.info(f"=== EXTRACT_SCHEMA DEBUG START ===")
        logger.info(f"Database type: {self.db_type}")
        logger.info(f"Session: {session}")
        logger.info(f"Metadata: {metadata}")
        logger.info(f"Schema info file key: {schema_info_file_key}")
        
        if self.db_type == 's3':
            logger.info(f"Processing S3 schema extraction")
            if session == 'new':
                logger.info(f"New session - extracting from S3")
                self._extract_schema_from_s3(metadata)
            else:
                try:
                    logger.info(f"Existing session - loading from: {schema_info_file_key}")
                    response = self.s3_client.get_object(Bucket = os.environ.get("S3_BUCKET_NAME"), Key=schema_info_file_key)
                    body_content = response['Body'].read()
                    self.schema_info = json.loads(body_content)
                    logger.info(f"Schema info loaded successfully: {len(self.schema_info)} tables")
                    for table_name in self.schema_info.keys():
                        logger.info(f"  - Table: {table_name}")
                except Exception as e:
                    logger.error(f"Failed to load existing schema info: {e}")
                    logger.info("Falling back to extracting new schema info") 
                    self._extract_schema_from_s3(metadata)
        else:
            logger.info(f"Processing database schema extraction")
            self._extract_schema_from_db(metadata)
        
        logger.info(f"Schema extraction completed. Found {len(self.schema_info)} tables")
        logger.info(f"=== EXTRACT_SCHEMA DEBUG END ===")

    def _extract_schema_from_db(self, metadata):
        """Extract schema information using SQLAlchemy inspector"""
        logger.info(f"=== _EXTRACT_SCHEMA_FROM_DB DEBUG START ===")
        
        if not self.engine:
            raise ConnectionError("Database connection not established")

        try:
            is_meta = metadata.get('is_meta', False)
            logger.info(f"Is metadata available: {is_meta}")
            
            if is_meta:
                try:
                    table_meta = metadata['table_meta']
                    s3_bucket_name = metadata['s3_bucket_name']
                    logger.info(f"Processing table metadata from: {table_meta}")
                    table_meta_response = s3.get_object(Bucket=s3_bucket_name, Key=table_meta)
                    table_meta = pd.read_excel(io.BytesIO(table_meta_response['Body'].read()))
                    tab_meta_tables = table_meta['Table Name'].unique().tolist()
                    logger.info(f"Tables from metadata: {tab_meta_tables}")
                except Exception as e:
                    logger.error(f"Failed to process table metadata: {e}")
                    tab_meta_tables = None
            else:
                tab_meta_tables = None

            inspector = inspect(self.engine)
            all_tables = list(set(inspector.get_table_names()))
            logger.info(f"All tables found in database: {all_tables}")
            
            if tab_meta_tables:
                tables = list(set(all_tables) & set(tab_meta_tables))
                logger.info(f"Filtered tables (intersection): {tables}")
            else:
                tables = all_tables
                logger.info(f"Using all tables: {tables}")

            for table_name in tables:
                logger.info(f"Processing table: {table_name}")
                table_info = {
                    'columns': [],
                    'primary_keys': [],
                    'foreign_keys': [],
                    'distinct_values': {}
                }

                # Get column information
                columns = inspector.get_columns(table_name)
                logger.info(f"  Found {len(columns)} columns")
                
                for column in columns:
                    nullable_str = "nullable" if column.get('nullable', True) else "not null"
                    column_info = f"{column['name']} ({column['type']}, {nullable_str})"
                    table_info['columns'].append(column_info)

                # Get primary key information
                pk_constraint = inspector.get_pk_constraint(table_name)
                if pk_constraint and 'constrained_columns' in pk_constraint:
                    table_info['primary_keys'] = pk_constraint['constrained_columns']
                    logger.info(f"  Primary keys: {table_info['primary_keys']}")

                # Get foreign key information
                fk_list = inspector.get_foreign_keys(table_name)
                for fk in fk_list:
                    fk_info = {
                        'constrained_columns': fk['constrained_columns'],
                        'referred_table': fk['referred_table'],
                        'referred_columns': fk['referred_columns']
                    }
                    table_info['foreign_keys'].append(fk_info)
                
                logger.info(f"  Foreign keys: {len(table_info['foreign_keys'])}")

                self.schema_info[table_name] = table_info
                logger.info(f"  Table {table_name} processed successfully")

            logger.info(f"Calling extract_distinct_values...")
            self.extract_distinct_values()
            logger.info(f"Distinct values extraction completed")

        except Exception as e:
            logger.error(f"Error in _extract_schema_from_db: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise Exception(f"Failed to extract schema: {str(e)}")
        
        logger.info(f"=== _EXTRACT_SCHEMA_FROM_DB DEBUG END ===")
            
    def _extract_schema_from_s3(self, metadata):
        """Extract schema information from CSV files in S3"""
        logger.info(f"=== _EXTRACT_SCHEMA_FROM_S3 DEBUG START ===")
        
        if not self.s3_client or not self.bucket_name:
            raise ConnectionError("S3 connection not established")

        try:
            csv_files = []
            logger.info(f"S3 bucket: {self.bucket_name}")
            logger.info(f"S3 prefix: {self.prefix}")
            
            # List objects in the bucket with the given prefix database
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix=f"{self.prefix}/data")
            
            logger.info(f"Listing objects with prefix: {self.prefix}/data")
            
            for page in pages:
                if 'Contents' in page:
                    logger.info(f"Found page with {len(page['Contents'])} objects")
                    for obj in page['Contents']:
                        if obj['Key'].endswith('.csv'):
                            csv_files.append(obj['Key'])
                            logger.info(f"  Found CSV: {obj['Key']}")
                else:
                    logger.warning("No contents found in page")
            
            self.csv_files = csv_files
            logger.info(f"Total CSV files found: {len(csv_files)}")
            logger.info(f"CSV files: {csv_files}")
            
            # Process table metadata if provided
            is_meta = metadata.get('is_meta', False)
            logger.info(f"Processing metadata: {is_meta}")
            
            if is_meta:
                try:
                    table_meta_key = f"{self.prefix}/metadata/{self.prefix}_tables.xlsx"
                    logger.info(f"Loading table metadata from: {table_meta_key}")
                    table_meta_response = self.s3_client.get_object(Bucket=self.bucket_name, Key=table_meta_key)
                    try: 
                        # Save the Excel file content for debugging
                        excel_content = table_meta_response['Body'].read()
                        logger.info(f"Excel file size: {len(excel_content)} bytes")
                        
                        # Try to read the Excel file
                        table_meta = pd.read_excel(io.BytesIO(excel_content), engine='openpyxl')
                        
                        # Check if 'Table Name' column exists
                        if 'Table Name' in table_meta.columns:
                            tab_meta_tables = table_meta['Table Name'].unique().tolist()
                            logger.info(f"Found tables in metadata: {tab_meta_tables}")
                        else:
                            logger.warning(f"Excel file columns: {table_meta.columns.tolist()}")
                            tab_meta_tables = None
                            logger.warning("'Table Name' column not found in metadata file")
                    except Exception as excel_error:
                        tab_meta_tables = None
                        logger.error(f"Failed to read table metadata: {str(excel_error)}")

                    column_meta_key = f"{self.prefix}/metadata/{self.prefix}_columns.xlsx"
                    logger.info(f"Loading column metadata from: {column_meta_key}")
                    column_meta_response = self.s3_client.get_object(Bucket=self.bucket_name, Key=column_meta_key)
                    try:
                        # Save the Excel file content for debugging
                        column_excel_content = column_meta_response['Body'].read()
                        logger.info(f"Column Excel file size: {len(column_excel_content)} bytes")
                        
                        # Try to read the Excel file
                        column_meta = pd.read_excel(io.BytesIO(column_excel_content), engine='openpyxl')
                        
                        # Check if expected columns exist
                        expected_columns = ['Table Name', 'Column Name', 'Column Description']
                        missing_columns = [col for col in expected_columns if col not in column_meta.columns]
                        
                        if missing_columns:
                            logger.warning(f"Missing columns in metadata file: {missing_columns}")
                            logger.warning(f"Available columns: {column_meta.columns.tolist()}")
                        else:
                            logger.info(f"Column metadata loaded successfully with {len(column_meta)} rows")
                    except Exception as excel_error:
                        column_meta = None
                        logger.error(f"Failed to read column metadata: {str(excel_error)}")

                except Exception as e:
                    logger.error(f"Failed to load metadata files: {e}")
                    tab_meta_tables = None
                    column_meta = None
            else:
                tab_meta_tables = None
                column_meta = None
             
            logger.info(f"Processing {len(csv_files)} CSV files...")
            
            for csv_file in csv_files:
                # Extract table name from file path
                table_name = os.path.splitext(os.path.basename(csv_file))[0]
                logger.info(f"Processing CSV file: {csv_file} -> Table: {table_name}")
                
                # Process all tables if no metadata or if table is in metadata
                if tab_meta_tables is not None and table_name not in tab_meta_tables:
                    logger.info(f"  Skipping {table_name} - not in metadata tables")
                    continue                
                try:                    
                    # Read CSV header and sample rows to infer schema
                    logger.info(f"  Reading CSV file: {csv_file}")
                    response = self.s3_client.get_object(Bucket=self.bucket_name, Key=csv_file)
                    df = pd.read_csv(io.BytesIO(response['Body'].read()), nrows=100)  # Read first 100 rows for schema inference
                    logger.info(f"  CSV loaded: {df.shape[0]} rows, {df.shape[1]} columns")
                    
                    table_info = {
                        'columns': [],
                        'primary_keys': [],
                        'foreign_keys': [],
                        'distinct_values': {},
                        'data_types': [],
                    }
                    
                    # Get column information
                    logger.info(f"  Processing {len(df.columns)} columns...")
                    for column_name, dtype in df.dtypes.items():
                        if is_numeric_dtype(df[column_name]):
                            if all(df[column_name].dropna().apply(lambda x: int(x) == x)):
                                col_type = "INT"
                            else:
                                col_type = "DOUBLE"
                        elif is_datetime64_any_dtype(df[column_name]):
                            col_type = "TIMESTAMP"
                        elif is_string_dtype(df[column_name]):
                            col_type = "STRING"
                        else:
                            col_type = "STRING"  # Default type                        
                        # Check for nullability
                        nullable = df[column_name].isnull().any()
                        nullable_str = "nullable" if nullable else "not null"
                        
                        # Get column description from metadata if available
                        column_desc = ""
                        if column_meta is not None:
                            column_desc = column_meta.loc[
                                (column_meta['Table Name'] == table_name) & 
                                (column_meta['Column Name'] == column_name),
                                'Column Description'
                            ].values[0] if len(column_meta.loc[
                                (column_meta['Table Name'] == table_name) & 
                                (column_meta['Column Name'] == column_name)
                            ]) > 0 else ""
                            
                        column_info = f"{column_name} ({col_type}, {nullable_str}), Column description: {column_desc}"
                        table_info['columns'].append(column_info)
                        table_info['data_types'].append({column_name: col_type})
                                               
                        # Sample distinct values (up to 20)
                        distinct_values = df[column_name].dropna().unique()[:5].tolist()
                        table_info['distinct_values'][column_name] = distinct_values

                    logger.info(f"  Table info for {table_name}: {len(table_info['columns'])} columns, {len(table_info['distinct_values'])} distinct value sets")
                    
                    self.schema_info[table_name] = table_info
                    logger.info(f"  Table {table_name} added to schema_info")
                    
                except Exception as e:
                    logger.error(f"  Error processing CSV file {csv_file}: {str(e)}")
            
            logger.info(f"S3 schema extraction completed. Total tables: {len(self.schema_info)}")
            
        except Exception as e:
            logger.error(f"Error in _extract_schema_from_s3: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise Exception(f"Failed to extract schema from S3: {str(e)}")
        
        logger.info(f"=== _EXTRACT_SCHEMA_FROM_S3 DEBUG END ===")

    def extract_distinct_values(self, max_values_per_column=20):
        """Extract distinct values for each column up to a specified limit."""
        if self.db_type == 's3':
            # For S3, distinct values are already extracted during schema extraction
            return
        
        if not self.engine:
            raise ConnectionError("Database connection not established")

        try:
            inspector = inspect(self.engine)
            for table_name, table_info in self.schema_info.items():
                with self.engine.connect() as connection:
                    for column in inspector.get_columns(table_name):
                        column_name = column['name']
                        distinct_values = []
                        try:
                            query = select(distinct(text(column_name))).select_from(text(table_name)).limit(max_values_per_column)
                            result = connection.execute(query)
                            logger.info(result)
                            distinct_values = [row[0] for row in result]
                        except OperationalError as e:
                            logger.error(f"Could not retrieve distinct values for {table_name}.{column_name}: {e}")
                        self.schema_info[table_name]['distinct_values'][column_name] = distinct_values
        except Exception as e:
            raise Exception(f"Failed to extract distinct values: {str(e)}")

    def get_schema_string(self):
        """Format schema information as a string, including distinct values."""
        logger.info(f"=== GET_SCHEMA_STRING DEBUG START ===")
        logger.info(f"Schema info available: {bool(self.schema_info)}")
        logger.info(f"Number of tables in schema_info: {len(self.schema_info) if self.schema_info else 0}")
        
        if self.schema_info:
            for table_name in self.schema_info.keys():
                logger.info(f"  Table: {table_name}")
        
        schema_str = "Database Schema:\n"
        
        if not self.schema_info:
            logger.warning("WARNING: schema_info is empty, returning basic schema string")
            return schema_str
            
        for table, info in self.schema_info.items():
            logger.info(f"Processing table {table} with info keys: {list(info.keys())}")
            schema_str += f"*****TABLE {table} starts*****\n"

            # Add columns
            schema_str += "Columns:\n"
            for column in info['columns']:
                schema_str += f"  - {column}\n"

            # Add primary keys if present
            if info['primary_keys']:
                schema_str += "Primary Keys:\n"
                for pk in info['primary_keys']:
                    schema_str += f"  - {pk}\n"

            # Add foreign keys if present
            if info['foreign_keys']:
                schema_str += "Foreign Keys:\n"
                for fk in info['foreign_keys']:
                    constrained = ', '.join(fk['constrained_columns'])
                    referred = ', '.join(fk['referred_columns'])
                    schema_str += f"  - {constrained} -> {fk['referred_table']}({referred})\n"

            # Add distinct values if present
            if info['distinct_values']:
                schema_str += "Distinct Values:\n"
                for column, values in info['distinct_values'].items():
                    values_str = ', '.join(map(str, values))
                    schema_str += f"  - {column}: {values_str}\n"

            schema_str += f"*****TABLE {table} ends*****\n\n"
        
        logger.info(f"Generated schema string length: {len(schema_str)}")
        logger.info(f"=== GET_SCHEMA_STRING DEBUG END ===")
        return schema_str

    def get_schema_info(self):
        """Return the raw schema information dictionary"""
        return self.schema_info