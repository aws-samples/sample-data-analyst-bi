import os
import json
import pandas as pd
import re
from scripts.prompts import (
    query_text_tab_tempv3,
    filter_tables_system_prompt,
    LLM_PROMPTS_FINAL,
)
from scripts.utils import init_bedrock_llm, init_sagemaker_llm, log_error
import ast


def check_table_access(table_access, tables_list):
    if table_access:
        table_access = pd.read_excel(table_access)
        common_tabs = list(
            set(table_access["table_name"]).intersection(set(tables_list))
        )
        if common_tabs:
            message = "Your question requires access to certain tables which you don't have access to"
        else:
            message = None
    else:
        message = None
    return message


def create_schema_meta(
    schema, tab_meta, col_meta, tables_list, foreign_key_list, is_meta, distinct_values, metric_meta=None
):
    """Formats schema metadata, including tables, columns, descriptions, constraints, and distinct values.

    Args:
        schema (DataFrame): Schema details (table names, column names, types, constraints).
        tab_meta (DataFrame): Metadata containing table descriptions.
        col_meta (DataFrame): Metadata containing column descriptions.
        tables_list (list): List of tables to include (None = all tables).
        foreign_key_list (str): Pipe-separated foreign key details.
        is_meta (bool): Whether to use table/column metadata.
        distinct_values (DataFrame): DataFrame containing distinct values for each column.
        metric_meta (DataFrame): Metadata containing metric names and descriptions.

    Returns:
        str: Formatted schema metadata string.
    """
    try:
        schema_str = ""
        filtered_foreign_key = ""

        tables = tables_list if tables_list else schema["table_name"].unique().tolist()
        print("tables inside create_schema_meta", tables)

        # Add metrics section if metric_meta is provided
        if metric_meta not in [None, '']:
            print("metric_meta", metric_meta)
            schema_str += "Metrics:\n"
            metric_meta.columns = metric_meta.columns.str.strip()
            
            for _, row in metric_meta.iterrows():
                metric_name = row["Metric Name"]
                metric_desc = row["Description"]
                schema_str += f"  Metric Name: {metric_name}\n"
                schema_str += f"    Description: {metric_desc}\n"
            
            schema_str += "\n"

        if is_meta:
            # Filter metadata tables and columns
            tab_meta_tables = tab_meta["Table Name"].unique().tolist()
            filtered_tables = list(set(tables) & set(tab_meta_tables)) #change2
            col_meta.columns = col_meta.columns.str.strip()
            tab_meta.columns = tab_meta.columns.str.strip()
            cols_meta = col_meta["Column Name"].values.tolist()
            schema = schema[schema["column_name"].isin(cols_meta)] #change2

            for tab in filtered_tables:
                schema_str += f"Table Name: {tab}\n"

                # Get table description
                tab_desc = None
                if tab_meta.shape[0] > 0 and "Comments" in tab_meta.columns:
                    tab_desc = tab_meta[tab_meta["Table Name"] == tab]["Comments"].tolist()[0]

                if tab_desc:
                    schema_str += f"Table Description: {tab_desc}\n"

                cols = schema[schema["table_name"] == tab]["column_name"].tolist()

                for col in cols:
                    col_desc = None
                    if col_meta.shape[0] > 0 and "Column Description" in col_meta.columns:
                        col_desc_list = col_meta[col_meta["Column Name"] == col]["Column Description"].tolist()
                        col_desc = col_desc_list[0] if col_desc_list else None

                    col_data_type = schema[schema["column_name"] == col]["data_type"].tolist()[0]

                    col_key_type = schema[schema["column_name"] == col]["key_type"].tolist()[0]
                    col_key_type = "No Key Constraint" if col_key_type == "None" else col_key_type

                    schema_str += f"  Column Name: {col}\n"
                    if col_desc:
                        schema_str += f"    Column Description: {col_desc}\n"
                    schema_str += f"    Data Type: {col_data_type}\n"
                    schema_str += f"    Key Constraint: {col_key_type}\n"

                    # Add distinct values if available
                    col_key = f"{tab}.{col}"
                    if col_key in distinct_values["column"].values:
                        values = distinct_values[distinct_values["column"] == col_key]["distinct_values"].values[0]
                        schema_str += f"    Distinct Values: {values}\n"

                schema_str += "\n"

                # Handle foreign keys
                try:
                    foreign_key_split = foreign_key_list.split("|")
                    for item in foreign_key_split:
                        filtered_data = (item.split(":")[0]).strip()
                        if tab.lower() == filtered_data.lower():
                            filtered_foreign_key += item + "|"
                except:
                    continue

            if not filtered_foreign_key:
                filtered_foreign_key = foreign_key_list

            print("filtered_foreign_key", filtered_foreign_key)
            schema_str += f"Foreign Keys: {filtered_foreign_key}\n"

        else:
            print("schema shape", schema.shape)
            for tab in tables:
                print("tab",tab)
                schema_str += f"Table Name: {tab}\n"
                table_schema = schema[schema["table_name"] == tab]
                print("table_schema", table_schema)

                for _, row in table_schema.iterrows():
                    col_name = row["column_name"]
                    col_data_type = row["data_type"]
                    col_key_type = row["key_type"]
                    col_key_type = "No Key Constraint" if col_key_type == "None" else col_key_type

                    schema_str += f"  Column Name: {col_name}\n"
                    schema_str += f"    Data Type: {col_data_type}\n"
                    schema_str += f"    Key Constraint: {col_key_type}\n"

                    # Add distinct values
                    col_key = f"{tab}.{col_name}"
                    if col_key in distinct_values["column"].values:
                        values = distinct_values[distinct_values["column"] == col_key]["distinct_values"].values[0]
                        schema_str += f"    Distinct Values: {values}\n"

                schema_str += "\n"
                print("schema_str", schema_str)

                # Handle foreign keys
                try:
                    foreign_key_split = foreign_key_list.split("|")
                    for item in foreign_key_split:
                        filtered_data = (item.split(":")[0]).strip()
                        if tab.lower() == filtered_data.lower():
                            filtered_foreign_key += item + "|"
                except:
                    continue

            if not filtered_foreign_key:
                filtered_foreign_key = foreign_key_list

            print("filtered_foreign_key", filtered_foreign_key)
            schema_str += f"Foreign Keys: {filtered_foreign_key}\n"

        return schema_str

    except Exception as e:
        print("create_schema_meta :::", e)
        return None

def filter_tables(text_query, schema_meta, table_access, model_id):
    try:
        fshot_prompt = query_text_tab_tempv3.format(
            schema=schema_meta, question=text_query
        )
        if model_id.startswith('ic-'):
            llm = init_sagemaker_llm(model_id)
            response = llm(fshot_prompt, system_prompt=filter_tables_system_prompt)
        else:
            llm = init_bedrock_llm(model_id)
            if "{sys_prompt}" in LLM_PROMPTS_FINAL[model_id]:
                final_prompt = LLM_PROMPTS_FINAL[model_id].format(
                    sys_prompt=filter_tables_system_prompt, sql_prompt=fshot_prompt
                )
            response = llm(final_prompt, system_prompt=filter_tables_system_prompt)
        print("filter_tables_response", response)
        tables_list_match = re.search(
            r"<tables_list>\s*(.*?)\s*</tables_list>", response, re.DOTALL
        )
        tables_list = ast.literal_eval(tables_list_match.group(1)) if tables_list_match else []
        print(tables_list)
        print(table_access)
        # schema_match = re.search(
        #     r"<schema>\s*(.*?)\s*</schema>", response, re.DOTALL)
        # filtered_tables_schema = json.loads(schema_match.group(1)) if schema_match else None
        if table_access:
            message = check_table_access(table_access, tables_list)
        else:
            message = None
        return message, tables_list
    except Exception as e:
        log_error("filter_tables :: ", e)
        print("filter_tables :: ", e)
        return None, None

def filter_table_info(schema_str: str, table_list: set) -> str:
    """
    Filter table information and foreign keys from schema string
    """
    result_lines = []
    foreign_key_line = None
    current_table = None
    is_target_table = False
    
    # Check if schema_str has the S3/Athena format with TABLE starts/ends markers
    if "*****TABLE" in schema_str:
        # S3/Athena format
        current_table_content = []
        capturing = False
        
        for line in schema_str.splitlines():
            if line.startswith("*****TABLE") and "starts*****" in line:
                table_name = line.replace("*****TABLE", "").replace("starts*****", "").strip()
                if table_name in table_list:
                    capturing = True
                    current_table_content = [line]
                else:
                    capturing = False
            elif line.startswith("*****TABLE") and "ends*****" in line:
                if capturing:
                    current_table_content.append(line)
                    result_lines.extend(current_table_content)
                capturing = False
            elif capturing:
                current_table_content.append(line)
    else:
        for line in schema_str.splitlines():
            stripped_line = line.strip()
            if stripped_line.startswith('Foreign Keys:'):
                foreign_key_line = line
                continue
            if stripped_line.startswith('Table Name:'):
                try:
                    current_table = stripped_line.replace('Table Name:', '', 1).strip()
                    is_target_table = current_table in table_list
                except Exception:
                    continue
                
            if is_target_table:
                result_lines.append(line)
        if foreign_key_line:
            result_lines.append(foreign_key_line)
    
    return '\n'.join(result_lines)