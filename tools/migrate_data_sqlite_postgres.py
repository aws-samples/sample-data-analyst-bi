import psycopg2
import sqlite3
import pandas as pd
import re
from psycopg2 import Error
from pathlib import Path
from datetime import datetime, timezone
import requests
import json
from typing import Dict, List, Any
import os
import boto3
import pandas as pd
import base64
from config import db_config, sqlite_dir
from collections import defaultdict


def sanitize_column_name(name):
    return re.sub(r'^%', 'percent_', re.sub(r'[^\w]+', '_', name)).strip('_').lower()

def get_table_dependencies(sqlite_cursor):
    """Build a dependency graph of tables based on foreign keys"""
    dependencies = defaultdict(set)
    sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [table[0] for table in sqlite_cursor.fetchall()]
    
    for table in tables:
        sqlite_cursor.execute(f"PRAGMA foreign_key_list([{table}])")
        foreign_keys = sqlite_cursor.fetchall()
        for fk in foreign_keys:
            dependencies[table].add(fk[2])
    
    return dependencies

def get_table_creation_order(dependencies):
    """Return tables in order of creation based on dependencies"""
    ordered_tables = []
    all_tables = set(dependencies.keys()).union(*dependencies.values())
    remaining_tables = all_tables.copy()
    
    while remaining_tables:
        available_tables = {
            table for table in remaining_tables
            if not dependencies.get(table, set()) - set(ordered_tables)
        }
        
        if not available_tables:
            raise ValueError("Circular dependency detected")
            
        for table in sorted(available_tables):
            ordered_tables.append(table)
            remaining_tables.remove(table)
            
    return ordered_tables



def sqlite_to_postgres(sqlite_file, db_params):
    """
    Migrate SQLite database to PostgreSQL with transaction safety and foreign key violation handling
    """
    try:
        sqlite_conn = None
        pg_conn = None
        success = False

        # Add structure to track invalid records
        invalid_records = {
            'counts': defaultdict(int),
            'details': defaultdict(list)
        }

        try:
            # [Your existing connection code remains the same]
            # Connect to both databases
            sqlite_conn = sqlite3.connect(sqlite_file)
            sqlite_cursor = sqlite_conn.cursor()

            pg_conn = psycopg2.connect(**db_params)
            # Disable autocommit to handle transaction manually
            pg_conn.autocommit = False
            pg_cursor = pg_conn.cursor()

            print("Starting migration process...")
            print("Getting table dependencies...")

            # Get dependencies and table creation order
            dependencies = get_table_dependencies(sqlite_cursor)
            table_order = get_table_creation_order(dependencies)
            print(f"Tables will be processed in this order: {table_order}")

             # Dictionary to store table statistics
            migration_stats = {
                'tables_processed': 0,
                'total_records_migrated': 0,
                'table_record_counts': {}
            }

            # First pass: Create all tables without foreign keys
            print("\nPhase 1: Creating table structures...")
            for table_name in table_order:
                print(f"\nProcessing structure for table: {table_name}")

                # Get table schema
                sqlite_cursor.execute(f"PRAGMA table_info([{table_name}])")
                schema = sqlite_cursor.fetchall()

                # Create table definition
                columns = []
                primary_keys = []

                for col in schema:
                    col_name = sanitize_column_name(col[1])
                    col_type = col[2].upper()
                    pk_index = col[5]  # Get primary key index # Added code

                    # Type conversion
                    if col_type == 'INTEGER PRIMARY KEY':
                        col_type = 'SERIAL PRIMARY KEY'
    #                     primary_keys.append(col_name)
                        primary_keys.append((pk_index, col_name)) # Added code
                    elif col_type == 'INTEGER':
                        col_type = 'INTEGER'
                    elif col_type == 'REAL':
                        col_type = 'DOUBLE PRECISION'
                    elif col_type == 'TEXT':
                        col_type = 'TEXT'
                    else:
                        col_type = 'TEXT'

                    if col[3] == 1:  # NOT NULL
                        col_type += ' NOT NULL'

                    columns.append(f"\"{col_name}\" {col_type}")

    #                 if col[5] == 1:  # Primary key
    #                     primary_keys.append(col_name)

                    if pk_index > 0:  # Primary key
                        primary_keys.append((pk_index, col_name))

                    # Sort primary keys by their index and extract just the names
                primary_keys.sort()  # Sort by pk index
                primary_keys = [pk[1] for pk in primary_keys]  # Extract just the names in correct order

                columns_sql = ", ".join(columns)
                if primary_keys and 'PRIMARY KEY' not in columns_sql:
    #                 columns_sql += f", PRIMARY KEY ({', '.join(f'"{pk}"' for pk in primary_keys)})"
    #                 columns_sql += f", PRIMARY KEY ({', '.join([f'\"{pk}\"' for pk in primary_keys])})"
                    columns_sql += ", PRIMARY KEY (" + ", ".join('"' + pk + '"' for pk in primary_keys) + ")"


                create_table_sql = f'DROP TABLE IF EXISTS "{table_name}" CASCADE; CREATE TABLE "{table_name}" ({columns_sql});'
                pg_cursor.execute(create_table_sql)
                print(f"Created table structure: {table_name}")

            # Modify Phase 2: Copying data with validation
            print("\nPhase 2: Copying data...")
            for table_name in table_order:
                print(f"\nCopying data for table: {table_name}")

                # Get foreign key information for validation
                sqlite_cursor.execute(f"PRAGMA foreign_key_list([{table_name}])")
                foreign_keys = sqlite_cursor.fetchall()

                # Get data from SQLite
                sqlite_cursor.execute(f"PRAGMA table_info([{table_name}])")
                table_info = sqlite_cursor.fetchall()
                column_names = [sanitize_column_name(col[1]) for col in table_info]

                sqlite_cursor.execute(f"SELECT * FROM [{table_name}]")
                rows = sqlite_cursor.fetchall()
                valid_rows = []

                # Validate foreign key constraints before insertion
                for row in rows:
                    row_dict = dict(zip(column_names, row))
                    is_valid = True

                    for fk in foreign_keys:
                        fk_column = sanitize_column_name(fk[3])
                        ref_table = fk[2].lower()
                        ref_column = sanitize_column_name(fk[4])
                        fk_value = row_dict.get(fk_column)

                        if fk_value is not None:
                            # Check if referenced value exists
                            pg_cursor.execute(
                                f'SELECT 1 FROM "{ref_table}" WHERE "{ref_column}" = %s LIMIT 1',
                                (fk_value,)
                            )
                            if not pg_cursor.fetchone():
                                is_valid = False
                                invalid_records['counts'][table_name] += 1
                                invalid_records['details'][table_name].append({
                                    'row': row_dict,
                                    'constraint': f'{fk_column} -> {ref_table}.{ref_column}',
                                    'value': fk_value
                                })
                                break

                    if is_valid:
                        valid_rows.append(row)

                # Insert valid rows
                if valid_rows:
                    columns_string = ', '.join(f'"{col}"' for col in column_names)
                    placeholders = ', '.join(['%s'] * len(column_names))
                    insert_query = f'INSERT INTO "{table_name}" ({columns_string}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'
                    pg_cursor.executemany(insert_query, valid_rows)

                    migration_stats['total_records_migrated'] += len(valid_rows)
                    migration_stats['table_record_counts'][table_name] = len(valid_rows)
                    print(f"Inserted {len(valid_rows)} valid rows into {table_name}")
                    if invalid_records['counts'][table_name] > 0:
                        print(f"Skipped {invalid_records['counts'][table_name]} invalid rows in {table_name}")
                else:
                    print(f"No valid data to copy for table: {table_name}")
                    migration_stats['table_record_counts'][table_name] = 0

            # [Your existing foreign key constraint creation code remains the same]
            # Third pass: Add all foreign key constraints
            print("\nPhase 3: Adding foreign key constraints...")
            for table_name in table_order:
                print(f"\nAdding foreign keys for table: {table_name}")

                sqlite_cursor.execute(f"PRAGMA foreign_key_list([{table_name}])")
                foreign_keys = sqlite_cursor.fetchall()

                for fk in foreign_keys:
                    fk_column = sanitize_column_name(fk[3])
                    ref_table = fk[2].lower()
                    ref_column = sanitize_column_name(fk[4])

                    fk_sql = f'ALTER TABLE "{table_name}" ADD CONSTRAINT ' \
                            f'fk_{table_name}_{fk_column} FOREIGN KEY ("{fk_column}") ' \
                            f'REFERENCES "{ref_table}" ("{ref_column}");'

                    pg_cursor.execute(fk_sql)
                    print(f"Added foreign key: {table_name}.{fk_column} -> {ref_table}.{ref_column}")


            # Modify verification phase
            print("\nPhase 4: Verifying migration...")
            for table_name in table_order:
                pg_cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                pg_count = pg_cursor.fetchone()[0]
                sqlite_cursor.execute(f'SELECT COUNT(*) FROM [{table_name}]')
                sqlite_count = sqlite_cursor.fetchone()[0]
                invalid_count = invalid_records['counts'][table_name]

                if pg_count + invalid_count != sqlite_count:
                    raise Exception(
                        f"Data verification failed for table {table_name}. "
                        f"Source had {sqlite_count} records, "
                        f"Target has {pg_count} records, "
                        f"Invalid records: {invalid_count}, "
                        f"Total: {pg_count + invalid_count}"
                    )
                print(f"Verified {pg_count} valid records and {invalid_count} invalid records in {table_name}")

            # Generate invalid records report
            if sum(invalid_records['counts'].values()) > 0:
                print("\nInvalid Records Report:")
                for table_name, count in invalid_records['counts'].items():
                    if count > 0:
                        print(f"\n{table_name}: {count} invalid records")
                        print("Sample of invalid records:")
                        for record in invalid_records['details'][table_name][:5]:  # Show up to 5 examples
                            print(f"  - Failed constraint: {record['constraint']}")
                            print(f"    Value: {record['value']}")

            success = True
            print("\nMigration completed successfully!")
            print(f"Total valid records migrated: {migration_stats['total_records_migrated']}")
            print(f"Total invalid records skipped: {sum(invalid_records['counts'].values())}")

        except Exception as e:
            print(f"\nError during migration: {str(e)}")
            if pg_conn:
                print("Rolling back all changes...")
                pg_conn.rollback()
            raise

        finally:
            # [Your existing cleanup code remains the same]
            if sqlite_conn:
                sqlite_conn.close()

            if pg_conn:
                if success:
                    print("\nCommitting all changes...")
                    pg_conn.commit()
                    print("Changes committed successfully!")
                else:
                    print("\nRolling back due to errors...")
                    pg_conn.rollback()
                pg_conn.close()
                
        return migration_stats, invalid_records
    
    except Exception as e:
        raise e
    
def check_postgres_db_exists(db_params, dbname):
    """Check if PostgreSQL database already exists"""
    temp_params = db_params.copy()
    temp_params['dbname'] = 'postgres'  # Connect to default database first
    try:
        conn = psycopg2.connect(**temp_params)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
        exists = cur.fetchone() is not None
        cur.close()
        conn.close()
        return exists
    except Exception as e:
        print(f"Error checking database existence: {str(e)}")
        return False

def create_postgres_db(db_params, dbname):
    """Create PostgreSQL database if it doesn't exist"""
    temp_params = db_params.copy()
    temp_params['dbname'] = 'postgres'
    try:
        conn = psycopg2.connect(**temp_params)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(f'CREATE DATABASE "{dbname}"')
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Error creating database: {str(e)}")
        return False

def list_sqlite_databases(directory):
    """List all SQLite databases in directory with their status"""
    all_files = []
    
    # Walk through directory
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(('.sqlite', '.db')):
                full_path = os.path.join(root, file)
                db_name = os.path.splitext(file)[0]
                all_files.append({
                    'name': db_name,
                    'path': full_path,
                    'size': os.path.getsize(full_path),
                    'modified': datetime.fromtimestamp(os.path.getmtime(full_path))
                })
    
    return all_files


def run_migrations(sqlite_dir, base_db_params, selected_dbs=None, output_dir='migration_reports'):
    """
    Wrapper function to run migrations for selected SQLite databases
    
    Args:
        sqlite_dir: Directory containing SQLite database files
        base_db_params: Base PostgreSQL connection parameters (without dbname)
        selected_dbs: List of database names to migrate (without extension)
        output_dir: Directory to save migration reports
    """
    # Create output directory if it doesn't exist
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Get all available SQLite databases
    available_dbs = list_sqlite_databases(sqlite_dir)
    
    if not available_dbs:
        raise ValueError(f"No SQLite databases found in {sqlite_dir}")
    
    # If no specific databases selected, show available ones and ask for selection
    if not selected_dbs:
        print("\nAvailable databases:")
        for i, db in enumerate(available_dbs):
            print(f"{i+1}. {db['name']} (Modified: {db['modified'].strftime('%Y-%m-%d %H:%M:%S')})")
        
        while True:
            try:
                selection = input("\nEnter database numbers to migrate (comma-separated) or 'all': ").strip()
                if selection.lower() == 'all':
                    selected_dbs = [db['name'] for db in available_dbs]
                    break
                else:
                    indices = [int(x.strip()) - 1 for x in selection.split(',')]
                    selected_dbs = [available_dbs[i]['name'] for i in indices]
                    break
            except (ValueError, IndexError):
                print("Invalid selection. Please try again.")
    
    # Filter available_dbs based on selection
    selected_db_files = [
        db for db in available_dbs
        if db['name'] in selected_dbs
    ]
    
    print(f"\nSelected {len(selected_db_files)} databases for migration")
    
    # Initialize DataFrame to store migration results
    migration_results = []
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    for db_file in selected_db_files:
        db_name = db_file['name']
        sqlite_file = db_file['path']
        
        print(f"\nProcessing database: {db_name}")
        
        # Check if PostgreSQL database already exists
        if check_postgres_db_exists(base_db_params, db_name):
            response = input(f"Database '{db_name}' already exists. Skip (s), Overwrite (o), or Cancel (c)? ").lower()
            if response == 's':
                print(f"Skipping {db_name}")
                continue
            elif response == 'c':
                print("Migration cancelled")
                break
            elif response == 'o':
                print(f"Will overwrite {db_name}")
            else:
                print("Invalid response, skipping")
                continue
        
        # Create database-specific connection parameters
        db_params = base_db_params.copy()
        db_params['dbname'] = db_name
        
        try:
            # Create PostgreSQL database
            if not check_postgres_db_exists(base_db_params, db_name):
                if not create_postgres_db(base_db_params, db_name):
                    raise Exception(f"Failed to create database {db_name}")
            
            # Initialize report data
            report_data = {
                'database_name': db_name,
                'sqlite_path': sqlite_file,
                'migration_timestamp': timestamp,
                'status': 'Failed',
                'total_records_migrated': 0,
                'total_records_invalid': 0,
                'error_message': None,
                'table_details': {}
            }
            
            # Run migration
            migration_stats, invalid_records = sqlite_to_postgres(sqlite_file, db_params)
            
            # Update report data
            report_data.update({
                'status': 'Success',
                'total_records_migrated': migration_stats['total_records_migrated'],
                'total_records_invalid': sum(invalid_records['counts'].values())
            })
            
            # Create detailed table report
            for table_name in migration_stats['table_record_counts']:
                report_data['table_details'][table_name] = {
                    'records_migrated': migration_stats['table_record_counts'][table_name],
                    'records_invalid': invalid_records['counts'].get(table_name, 0),
                    'invalid_details': invalid_records['details'].get(table_name, [])
                }
            
            # Save detailed report as JSON
            report_file = os.path.join(output_dir, f'{db_name}_migration_report_{timestamp}.json')
            detailed_report = {
                'migration_stats': migration_stats,
                'invalid_records': invalid_records,
                'report_data': report_data
            }
            with open(report_file, 'w') as f:
                json.dump(detailed_report, f, indent=2, default=str)
            
        except Exception as e:
            report_data.update({
                'status': 'Failed',
                'error_message': str(e)
            })
            print(f"Error processing {db_name}: {str(e)}")
        
        finally:
            migration_results.append(report_data)
    
    if not migration_results:
        print("No databases were migrated")
        return None, None
    
    # Create summary DataFrame
    summary_df = pd.DataFrame([
        {
            'Database': result['database_name'],
            'Status': result['status'],
            'Migration Timestamp': result['migration_timestamp'],
            'Total Records Migrated': result['total_records_migrated'],
            'Total Invalid Records': result['total_records_invalid'],
            'Error Message': result['error_message'],
            'SQLite Path': result['sqlite_path']
        }
        for result in migration_results
    ])
    
    # Create detailed DataFrame
    detailed_rows = []
    for result in migration_results:
        for table_name, table_data in result['table_details'].items():
            detailed_rows.append({
                'Database': result['database_name'],
                'Table': table_name,
                'Records Migrated': table_data['records_migrated'],
                'Invalid Records': table_data['records_invalid'],
                'Migration Timestamp': result['migration_timestamp']
            })
    
    detailed_df = pd.DataFrame(detailed_rows) if detailed_rows else None
    
    # Save DataFrames to CSV
    if not summary_df.empty:
        summary_csv = os.path.join(output_dir, f'migration_summary_{timestamp}.csv')
        summary_df.to_csv(summary_csv, index=False)
        print(f"\nSummary report saved: {summary_csv}")
    
    if detailed_df is not None and not detailed_df.empty:
        detailed_csv = os.path.join(output_dir, f'migration_detailed_{timestamp}.csv')
        detailed_df.to_csv(detailed_csv, index=False)
        print(f"Detailed report saved: {detailed_csv}")
    
    return summary_df, detailed_df

def main():
    
    # Directory containing SQLite database

    try:
        # Run migrations with interactive selection
        summary_df, detailed_df = run_migrations(sqlite_dir, db_config)
        if summary_df is not None:
            print("\nMigration Summary:")
            print(summary_df)
            
            if detailed_df is not None:
                print("\nDetailed Table Report:")
                print(detailed_df)
        
    except Exception as e:
        print(f"Error during migration process: {str(e)}")

if __name__ == "__main__":
    main()