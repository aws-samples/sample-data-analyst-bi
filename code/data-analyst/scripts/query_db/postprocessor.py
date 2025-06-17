import os
import sys
import re
import pandas as pd
import sqlite3
import boto3
from fuzzywuzzy import process, fuzz
from scripts.query_db.pgsql_executor import get_sql_result, get_sql_result2
import time


modelid = "anthropic.claude-3-sonnet-20240229-v1:0"
promptype = 'fewshot'


def convert_schema_dict_to_df(schema_dict):
    """Convert schema dictionary to pandas DataFrame with required structure"""
    rows = []
    for table_name, table_info in schema_dict.items():
        for column in table_info['columns']:
            # Split the column string into name and datatype
            # Example: "department (TEXT, nullable)" -> ["department", "TEXT, nullable"]
            column_parts = column.split(' (')
            column_name = column_parts[0]
            datatype = column_parts[1].rstrip(')') if len(column_parts) > 1 else ''
            
            rows.append({
                'table_name': table_name,
                'col_name': column_name,  # Just the column name without datatype
                'datatype': datatype
            })
        schema = pd.DataFrame(rows)
    return schema


def escape_sql_string(value):
    """
    Comprehensively escape a string for safe SQL usage
    """
    if not isinstance(value, str):
        return value
        
    # List of special characters to escape
    special_chars = {
        "'": "''",        # Single quote
        "\\": "\\\\",     # Backslash
        "\n": "\\n",      # Newline
        "\r": "\\r",      # Carriage return
        "\t": "\\t",      # Tab
        "\b": "\\b",      # Backspace
        "\f": "\\f",      # Form feed
        '"': '""',        # Double quote
        "%": "\\%",       # Percent sign (used in LIKE clauses)
        "_": "\\_",       # Underscore (used in LIKE clauses)
    }
    
    # Escape each special character
    escaped_value = value
    for char, replacement in special_chars.items():
        escaped_value = escaped_value.replace(char, replacement)
    
    return escaped_value

def extract_tab_components(sql, schema):
    """Extract table name, column names and filter values from SQL, handling aliases properly"""
    # First extract alias mappings from the SQL
    alias_pattern = r'(?i)FROM\s+(\w+)\s+(?:AS\s+)?(\w+)|JOIN\s+(\w+)\s+(?:AS\s+)?(\w+)'
    alias_matches = re.findall(alias_pattern, sql)
    
    # Create alias to table mapping
    alias_map = {}
    for match in alias_matches:
        if match[0] and match[1]:  # FROM clause matches
            alias_map[match[1]] = match[0]
        elif match[2] and match[3]:  # JOIN clause matches
            alias_map[match[3]] = match[2]
    
    print(f"Alias mapping: {alias_map}")
    
    # Modified patterns for filter conditions
    pattern1 = r"(\w+)\.(\w+)\s*=\s*'([^']*)'|(\w+)\.(\w+)\s*=\s*\"([^\"]*)\""  # handles both single and double quotes
    pattern2 = r"(\w+)\(([\w\.]+)\)\s*=\s*'([^']+)'"
    pattern3 = r"(\b\w+\b)\s*=\s*'([^']+)'"
    
    # print(f"Looking for pattern1 matches in: {sql}")
    matches1 = re.findall(pattern1, sql)
    print(f"Pattern1 matches: {matches1}")
    
    # print(f"Looking for pattern2 matches in: {sql}")
    matches2 = re.findall(pattern2, sql)
    print(f"Pattern2 matches: {matches2}")
    
    # print(f"Looking for pattern3 matches in: {sql}")
    matches3 = re.findall(pattern3, sql)
    print(f"Pattern3 matches: {matches3}")
    
    all_tables = list(schema['table_name'].unique())
    print(f"Available tables: {all_tables}")
    
    tab_comps = []
    
    # Handle table.column = 'value' pattern
    for match in matches1:
        # Handle both single and double quote matches
        if match[0]:  # single quote match
            alias, col, filter_val = match[0], match[1], match[2]
        else:  # double quote match
            alias, col, filter_val = match[3], match[4], match[5]
            
        print(f"Processing match - alias: {alias}, column: {col}, value: {filter_val}")
        
        # Convert alias to actual table name if it's an alias
        actual_table = alias_map.get(alias, alias)
        print(f"Converted {alias} to actual table: {actual_table}")
        
        if actual_table in all_tables:
            # Verify column exists in this table
            if not schema[(schema['table_name'] == actual_table) & 
                        (schema['col_name'] == col)].empty:
                tab_comps.append([actual_table, col, filter_val])
                print(f"Added component: [{actual_table}, {col}, {filter_val}]")
    
    # Handle function(table.column) = 'value' pattern
    for match in matches2:
        func, tab_col, filter_val = match
        if '.' in tab_col:
            alias, col = tab_col.split('.')
            actual_table = alias_map.get(alias, alias)
            if actual_table in all_tables:
                if not schema[(schema['table_name'] == actual_table) & 
                            (schema['col_name'] == col)].empty:
                    tab_comps.append([actual_table, col, filter_val])
    
    # Handle column = 'value' pattern (no explicit table reference)
    for match in matches3:
        col, filter_val = match
        # Find all tables that have this column
        matching_tables = schema[schema['col_name'] == col]['table_name'].unique()
        for table in matching_tables:
            if table in all_tables:
                tab_comps.append([table, col, filter_val])
    
    print(f"Final extracted components: {tab_comps}")

    # Deduplicate tab_comps before returning
    unique_tab_comps = []
    seen = set()
    
    for comp in tab_comps:
        comp_tuple = tuple(comp)  # Convert to tuple for hashing
        if comp_tuple not in seen:
            seen.add(comp_tuple)
            unique_tab_comps.append(comp)
    
    print(f"Final deduplicated components: {unique_tab_comps}")
    return unique_tab_comps

        

def normalize_values(tab_comps, sql, extractor):
    """This function replaces filter values with matching values from DB through fuzzy matching
       Uses token_set_ratio with threshold 92.
    Args:
        tab_comps (list[list]): list of table names, corresponding column names and filter values
        sql(str): the sql query
        extractor: Instance of class DatabaseSchemaExtractor
    Returns: the filter values from SQL, the top matching values from DB, the matching scores and the SQL
    """
    top_vals = []
    filter_vals = []
    scores = []
    sql_new = sql  # Create a new variable to store modified SQL
    value_replacements = []  # New list to store replacement messages
    
    for tab_grp in tab_comps:
        tab_name = tab_grp[0]
        col_name = tab_grp[1]
        filter_val = tab_grp[2]
        
        # Get distinct values from the column
        sql_temp = '''SELECT DISTINCT({}) FROM {}'''.format(col_name, tab_name)
        result, error = get_sql_result2(sql_temp, extractor)
        filter_val_act = result.values.ravel().tolist()
        
        # Find similar values using fuzzy matching
        output = process.extract(filter_val, filter_val_act, scorer=fuzz.token_set_ratio)
        print(f"Fuzzy match results for {filter_val}:", output)
        
        # Get matches above threshold
        top_matches = [out for out in output if (out[1] > 80 and out != filter_val)]
        
        if top_matches:  # If we found matches above threshold
            filter_act, score = top_matches[0]  # Get the best match
            scores.append(score)
            
            # Escape single quotes in the replacement value
            # filter_act_escaped = filter_act.replace("'", "''")
            # Escape the replacement value
            filter_act_escaped = escape_sql_string(filter_act)

            # # Create pattern that handles both single and double quotes
            # pattern = f"['\"]({re.escape(filter_val)})['\"]"
            # # sql_new = re.sub(pattern, f"'{filter_act}'", sql_new)
            # sql_new = re.sub(pattern, f"'{filter_act_escaped}'", sql_new)
            # # print(f"Replacing {filter_val} with {filter_act}")
            # print(f"Replacing {filter_val} with {filter_act_escaped}")

            # Replace the value in the SQL query
            sql_new = sql_new.replace(filter_val, filter_act_escaped)
            print(f"Replacing {filter_val} with {filter_act_escaped}")
            
            # Add replacement message to the list
            value_replacements.append(f"Replaced {filter_val} with {filter_act_escaped}")

            # Store top matches for reporting
            top_grp_vals = [top_matches[0][0]]  # Only keep the best match
            top_vals.append(top_grp_vals)
            filter_vals.append(filter_val)
            
        print('top_vals', top_vals)
        print('scores', scores)
    
    # Format the replacement messages as a numbered list
    if value_replacements:
        replacement_message = "Tried the following replacements -\n" + "\n".join(
            f"    {i+1}. {msg}" for i, msg in enumerate(value_replacements)
        )
    else:
        replacement_message = None

    return filter_vals, top_vals, scores, sql_new, replacement_message

    
    
def run_normalization_process(sql, result, extractor):
    """
    This function is to be used to decide whether filter values in a SQL are to be replaced based on the execution 
    results in DB

        Args:
            sql(str): the sql query
            result(DataFrame): the execution result of the SQL query in DB
            extractor : Instance of DatabaseSchemaExtractor
        Returns: The normalized SQL, the results of SQL execution and error messages if any
        
    """
    error = ''
    suggestion = ''
    replacement_message = ''
    if (result.shape[0] == 0) or ((result.shape[0]==1) and (None in result.values or 0 in result.values)):
        print('Modification required in SQL filters')
        schema_dict = extractor.get_schema_info()
        schema = convert_schema_dict_to_df(schema_dict)
        tab_comps = extract_tab_components(sql, schema)
        print('tab_comps', tab_comps)

        if not tab_comps:
                suggestion = "Normalization could not be performed as no filter conditions were found in the query."
                return sql, result, error, suggestion, replacement_message

        filter_val, top_vals, scores, sql_new, replacement_message = normalize_values(tab_comps, sql, extractor)
        print('sql_new', sql_new)
        
        if len(scores) > 0:  # If we have any matches above threshold
            # Try executing the modified SQL
            try:
                db_type = extractor.db_type
                if db_type == 's3':
                    gen_text = get_sql_from_athena(sql_new, extractor.prefix)
                else:
                    gen_text = get_sql_result(sql_new, extractor)
                result_new = gen_text[0]
                error_new = gen_text[1]
                
                if result_new.shape[0] > 0:  # If new SQL returns results
                    return sql_new, result_new, error, suggestion, replacement_message
                else:  # If new SQL still returns no results
                    if len(top_vals) > 0:
                        suggestion = f"No records exist even with suggested replacements. Original values: {filter_val}, Tried with: {top_vals}"
                    else:
                        suggestion = "No records exist. Try to rephrase the query with different entities"
                    return sql, pd.DataFrame(), error, suggestion, replacement_message

            except Exception as e:
                error = f"Error executing normalized query: {str(e)}"
                return sql_new, pd.DataFrame(), error, suggestion, replacement_message
        else:  # If no matches found at all
            suggestion = "No similar values found in the database. Try rephrasing the query with different entities"
            return sql, result, error, suggestion, replacement_message
            
    else:
        print('No modification required in SQL filters')
        return sql, result, error, suggestion, replacement_message

def get_sql_from_athena(sql, db_name):
    """Execute SQL query with Athena and return results in a format similar to get_sql_result.

    Args:
        sql (str): The SQL query to execute
        extractor (DatabaseSchemaExtractor): Instance containing database connection info

    Returns:
        List containing:
            - pd.DataFrame: Query results as a DataFrame (empty if error occurs)
            - str: Error message if any, empty string if successful
    """
    error_msg = ''
    df = pd.DataFrame()
    
    try:
        # Initialize Athena client
        athena_client = boto3.client('athena')
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        s3_output = f"s3://{bucket_name}/{db_name}/athena-output"
        
        # Execute query
        response = athena_client.start_query_execution(
            QueryString=sql,
            QueryExecutionContext={'Database': db_name},
            ResultConfiguration={'OutputLocation': s3_output}
        )
        
        # Get query execution ID
        query_execution_id = response['QueryExecutionId']
        
        # Wait for query to complete
        while True:
            response = athena_client.get_query_execution(QueryExecutionId=query_execution_id)
            state = response['QueryExecution']['Status']['State']
            if state in ['SUCCEEDED', 'FAILED', 'CANCELLED']:
                break
            time.sleep(1)
        
        # Check if query succeeded
        if state == 'SUCCEEDED':
            # Get query results
            results = athena_client.get_query_results(QueryExecutionId=query_execution_id)
            
            # Convert results to DataFrame
            columns = [col['Label'] for col in results['ResultSet']['ResultSetMetadata']['ColumnInfo']]
            data = []
            
            # Process data rows (skip header row)
            for row in results['ResultSet']['Rows'][1:]:
                data.append([col.get('VarCharValue', '') for col in row['Data']])
                
            df = pd.DataFrame(data, columns=columns)
            
            # Convert numeric columns
            for col in df.columns:
                try:
                    df[col] = pd.to_numeric(df[col])
                except:
                    pass
        else:
            # Query failed
            error_reason = response['QueryExecution']['Status'].get('StateChangeReason', 'Unknown error')
            error_msg = f"Query failed with status '{state}': {error_reason}"
            print(error_msg)
            
    except Exception as e:
        error_msg = str(e)
        print(f"Error executing Athena query: {error_msg}")
        
    return [df, error_msg]
