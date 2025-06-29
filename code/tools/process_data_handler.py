import json
import os
from botocore.config import Config
import boto3
import io
import pandas as pd
import openpyxl
from openpyxl.styles import Font

AWS_REGION = os.getenv('AWS_DEFAULT_REGION', 'ap-southeast-2')
MODEL_ID = os.getenv('CHAT_MODEL_ID', 'anthropic.claude-3-sonnet-20240229-v1:0')
BUCKET_NAME = os.environ.get('S3_BUCKET_NAME')
s3_client = boto3.client('s3')

def lambda_handler(event, context):
    """
    Processes CSV files and generates descriptions using Amazon Bedrock.
    """
    try:
        print(f"Event received: {json.dumps(event)}")
        
        # Extract parameters from the event
        project_id = event.get('projectId')
        extracted_path = event.get('extractedPath')
        
        if not project_id or not extracted_path:
            raise ValueError("Missing required parameters: projectId or extractedPath")

        # List objects in the bucket with the given prefix database
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=BUCKET_NAME, Prefix=f"{extracted_path}")
        
        csv_files = []
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    if obj['Key'].endswith('.csv'):
                        csv_files.append(obj)
            else:
                raise ValueError("No files found in the extracted path")    
        print(f"Found {len(csv_files)} CSV files to analyze")
        
        # Process each CSV file
        table_summaries = []
        
        for file in csv_files:
            file_key = file['Key']
            file_name = file_key.split('/')[-1]
            table_name = file_name.replace('.csv', '')
            
            print(f"Processing table: {table_name}")
            
            # Get the CSV file content
            obj = s3_client.get_object(Bucket=BUCKET_NAME, Key=file_key)
            csv_content = obj['Body'].read().decode('utf-8')
            
            # Parse CSV using pandas
            df = pd.read_csv(io.StringIO(csv_content))
            
            if len(df) == 0:
                print(f"No records found in {table_name}")
                continue
            
            # Create basic table summary with column names
            columns = [{'name': col} for col in df.columns]
            
            table_summaries.append({
                'tableName': table_name,
                'rowCount': len(df),
                'columns': columns,
                's3Key': file_key
            })
        print(table_summaries)
        
        # Generate descriptions using Bedrock
        generate_descriptions(table_summaries)
        
        # Create Excel files with descriptions
        table_xlsx_key, column_xlsx_key = create_excel_files(table_summaries, project_id)
        
        # Return the result
        return {
            'projectId': project_id,
            'status': 'COMPLETED',
            'tableXlsxKey': table_xlsx_key,
            'columnXlsxKey': column_xlsx_key
        }
        
    except Exception as e:
        print(f"Error processing data: {str(e)}")
        raise

def generate_descriptions(table_summaries):
    """
    Generates descriptions for tables and columns using Amazon Bedrock.
    """
    try:
        # Generate table descriptions
        table_prompt = generate_table_description_prompt(table_summaries)
        table_descriptions = get_bedrock_response(table_prompt)
        print(table_descriptions)
        
        # Parse and assign table descriptions
        parse_and_assign_table_descriptions(table_summaries, table_descriptions)
        
        # Generate all column descriptions in a single request
        column_prompt = generate_all_columns_description_prompt(table_summaries)
        column_descriptions = get_bedrock_response(column_prompt)
        parse_and_assign_all_column_descriptions(table_summaries, column_descriptions)
    
    except Exception as e:
        print(f"Error generating descriptions with Bedrock: {str(e)}")
        # Continue without descriptions if Bedrock fails

def generate_table_description_prompt(table_summaries):
    """
    Generates a prompt for table descriptions.
    """
    prompt = "I need concise, informative descriptions for these database tables. For each table, provide a single sentence that clearly explains its purpose, what specific data it stores, and its role in the database. Be specific about the entity or business concept each table represents.\n\n"
    
    prompt += "IMPORTANT: Do NOT just state the number of records and columns. Instead, focus on explaining:\n"
    prompt += "1. What real-world entity or concept the table represents\n"
    prompt += "2. What specific business data it stores\n"
    prompt += "3. How it relates to other tables if apparent from column names\n\n"
    prompt += "Examples of good descriptions:\n"
    prompt += "- account: Stores customer banking account information including account identifiers, associated district, frequency of statements, and creation date.\n"
    prompt += "- card: Contains information about payment cards issued to customers, including card type, issue date, and the disposition (account access rights) it's linked to.\n\n"
    
    for table in table_summaries:
        prompt += f"\nTABLE: {table['tableName']}\n"
        prompt += f"Row count: {table['rowCount']}\n"
        prompt += f"Columns: {', '.join(col['name'] for col in table['columns'])}\n"
    
    prompt += "\nFormat your response as:\n"
    prompt += "TABLE_NAME_1: Stores [specific data type] for [business purpose], including [key data points] for [entity type].\n"
    prompt += "TABLE_NAME_2: Contains [specific data type] related to [business function], tracking [key information] for [entity type].\n"
    prompt += "...and so on for each table."
    
    return prompt

def generate_column_description_prompt(table):
    """
    Generates a prompt for column descriptions.
    """
    prompt = f"I need concise, informative descriptions for columns in the \"{table['tableName']}\" table. "
    prompt += "For each column, provide a single sentence that explains what data it contains and its purpose. Is it a primary key or foreign key?\n"
    
    prompt += f"Table name: {table['tableName']}\n"
    if table.get('description'):
        prompt += f"Table description: {table['description']}\n"
    prompt += f"Columns: {', '.join(col['name'] for col in table['columns'])}\n\n"
    
    prompt += "Format your response as:\n"
    prompt += "COLUMN_NAME_1: Description of the first column\n"
    prompt += "COLUMN_NAME_2: Description of the second column\n"
    prompt += "...and so on for each column."
    
    return prompt

def generate_all_columns_description_prompt(table_summaries):
    """
    Generates a prompt for all columns across all tables.
    """
    prompt = "I need concise, informative descriptions for columns in these database tables. For each column, provide a single sentence that explains what data it contains and its purpose. Is it a primary key or foreign key?\n\n"
    
    for table in table_summaries:
        prompt += f"TABLE: {table['tableName']}\n"
        if table.get('description'):
            prompt += f"Table description: {table['description']}\n"
        prompt += f"Columns: {', '.join(col['name'] for col in table['columns'])}\n\n"
    
    prompt += "Format your response as:\n"
    prompt += "TABLE_NAME.COLUMN_NAME_1: Description of the first column\n"
    prompt += "TABLE_NAME.COLUMN_NAME_2: Description of the second column\n"
    prompt += "...and so on for each column in each table."
    
    return prompt

def get_bedrock_response(prompt):
    """
    Calls Amazon Bedrock to get a response.
    """
    try:
        bedrock_client = boto3.client("bedrock-runtime", region_name=AWS_REGION, config=Config(
            retries = {
                'max_attempts': 10,
                'mode': 'adaptive'
            }
        ))

        kwargs = {
            "modelId": MODEL_ID,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ],
            "system": [{
                "text": "You are a helpful assistant that provides concise descriptions."
            }],
            "inferenceConfig": {
                "temperature": 0,
                "topP": 1.0,
                "maxTokens": 4096  # Increased token limit for larger responses
            },
            "performanceConfig": {
                'latency': "standard"
            },
        }

        print(prompt.replace('\n', ''))
        
        # Implement exponential backoff for throttling
        import time
        max_retries = 5
        retry_delay = 2  # Initial delay in seconds
        
        for attempt in range(max_retries):
            try:
                response = bedrock_client.converse(**kwargs)
                outcome = response['output']['message']['content'][0]['text']
                print(f"Received response from Bedrock: {outcome}")
                return outcome
            except Exception as e:
                if 'ThrottlingException' in str(e) and attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    print(f"Throttling detected, retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    raise e
    
    except Exception as e:
        print(f"Error calling Bedrock: {str(e)}")
        return ''  # Return empty string instead of throwing

def parse_and_assign_table_descriptions(table_summaries, descriptions_text):
    """
    Parses and assigns table descriptions.
    """
    if not descriptions_text:
        return
    
    lines = descriptions_text.split('\n')
    
    for line in lines:
        match = line.split(':', 1)
        if len(match) == 2:
            table_name = match[0].strip()
            description = match[1].strip()
            
            for table in table_summaries:
                if table['tableName'].lower() == table_name.lower():
                    table['description'] = description
                    break

def parse_and_assign_all_column_descriptions(table_summaries, descriptions_text):
    """
    Parses and assigns column descriptions.
    """
    if not descriptions_text:
        return
    
    lines = descriptions_text.split('\n')
    
    for line in lines:
        match = line.split(':', 1)
        if len(match) == 2:
            full_column_name = match[0].strip()
            description = match[1].strip()
            
            # Check if the format is TABLE_NAME.COLUMN_NAME
            if '.' in full_column_name:
                table_name, column_name = full_column_name.split('.', 1)
                
                # Find the table
                for table in table_summaries:
                    if table['tableName'].lower() == table_name.lower():
                        # Find the column
                        for column in table['columns']:
                            if column['name'].lower() == column_name.lower():
                                column['description'] = description
                                break
                        break
            else:
                # If no table name prefix, try to match just the column name
                # This is a fallback for simpler formats
                column_name = full_column_name
                for table in table_summaries:
                    for column in table['columns']:
                        if column['name'].lower() == column_name.lower():
                            column['description'] = description
                            break

def create_excel_files(table_summaries, filename):
    """
    Creates Excel files with table and column descriptions.
    """    
    # Create table description workbook
    table_wb = openpyxl.Workbook()
    table_ws = table_wb.active
    table_ws.title = "Table Descriptions"
    
    # Add headers
    table_ws.append(["Table Name", "Table Label", "Comments"])
    
    # Style header row
    for cell in table_ws[1]:
        cell.font = Font(bold=True)
    
    # Set column widths
    table_ws.column_dimensions['A'].width = 20
    table_ws.column_dimensions['B'].width = 30
    table_ws.column_dimensions['C'].width = 50
    
    # Add data rows
    for table in table_summaries:
        table_name = table['tableName']
        table_label = format_table_label(table_name)
        comments = table.get('description', f"Contains {table['rowCount']} records with {len(table['columns'])} columns")
        table_ws.append([table_name, table_label, comments])
    
    # Create column description workbook
    column_wb = openpyxl.Workbook()
    column_ws = column_wb.active
    column_ws.title = "Column Descriptions"
    
    # Add headers - simplified as requested
    column_ws.append(["Table Name", "Column Name", "Column Description"])
    
    # Style header row
    for cell in column_ws[1]:
        cell.font = Font(bold=True)
    
    # Set column widths
    column_ws.column_dimensions['A'].width = 20
    column_ws.column_dimensions['B'].width = 20
    column_ws.column_dimensions['C'].width = 60
    
    # Add data rows
    for table in table_summaries:
        for column in table['columns']:
            column_ws.append([
                table['tableName'],
                column['name'],
                column.get('description', 'N/A')
            ])
    
    # Save workbooks to S3
    table_buffer = io.BytesIO()
    table_wb.save(table_buffer)
    table_buffer.seek(0)
    
    column_buffer = io.BytesIO()
    column_wb.save(column_buffer)
    column_buffer.seek(0)
    
    # Upload to S3 with the new path structure
    table_xlsx_key = f"{filename}/metadata/{filename}_tables.xlsx"
    s3_client.put_object(
        Bucket=BUCKET_NAME,
        Key=table_xlsx_key,
        Body=table_buffer.getvalue(),
        ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    
    column_xlsx_key = f"{filename}/metadata/{filename}_columns.xlsx"
    s3_client.put_object(
        Bucket=BUCKET_NAME,
        Key=column_xlsx_key,
        Body=column_buffer.getvalue(),
        ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    
    return table_xlsx_key, column_xlsx_key

def format_table_label(table_name):
    """
    Formats a table name into a readable label.
    """
    return ' '.join(word.capitalize() for word in table_name.split('_'))