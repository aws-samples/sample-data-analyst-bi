import os
import json
import pandas as pd
import boto3
import numpy as np
from numpy.linalg import norm
from botocore.config import Config
from botocore.exceptions import ClientError
import psycopg2
from psycopg2 import sql
from config import db_config, region_name
import pymysql

import re

my_config = Config(
    region_name = 'us-east-1',
    signature_version = 'v4',
    retries = {
        'max_attempts': 3,
        'mode': 'standard'
    }
)

bedrock_rt = boto3.client("bedrock-runtime", config = my_config)
s3_client = boto3.client("s3")

# def get_secret():

#     # Create a Secrets Manager client
#     session = boto3.session.Session()
#     client = session.client(
#         service_name='secretsmanager',
#         region_name=region_name
#     )

#     try:
#         get_secret_value_response = client.get_secret_value(
#             SecretId=secret_name
#         )
#     except ClientError as e:
#         # For a list of exceptions thrown, see
#         # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
#         raise e

#     secret = get_secret_value_response['SecretString']
#     return secret

def get_existing_columns(table_name):
    # Query to get existing columns of the table
    query = sql.SQL("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = %s
    """)
    
    cursor.execute(query, (table_name,))
    existing_columns = [row[0] for row in cursor.fetchall()]
    return existing_columns

def add_missing_columns(table_name, columns):
    existing_columns = get_existing_columns(table_name)
    columns_added = False
    
    for col in columns:
        col_name = col["name"]
        col_type = col["type"]
        if col_name not in existing_columns:
            alter_table_query = sql.SQL("""
                ALTER TABLE {table} ADD COLUMN {col_name} {col_type}
            """).format(
                table=sql.Identifier(table_name),
                col_name=sql.Identifier(col_name),
                col_type=sql.SQL(col_type)
            )
            cursor.execute(alter_table_query)
            print(f"Created column {col_name} in {table_name} successfully.")
            columns_added = True
        else:
            print(f"Column {col_name} already exists in {table_name}.")
    
    if columns_added:
        conn.commit()

def table_exists(cursor, table_name):
    query = sql.SQL("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables 
            WHERE table_name = %s
        );
    """)
    cursor.execute(query, (table_name,))
    return cursor.fetchone()[0]

def create_table(cursor, conn):
    create_table_sql = sql.SQL("""
        CREATE TABLE IF NOT EXISTS {table} (
            sql_query TEXT,
            explanation TEXT,
            generated_question TEXT,
            embedded_questions VECTOR(1024),
            confidence_scores numeric[]
        );
    """).format(table=sql.Identifier(table_name))

    cursor.execute(create_table_sql)
    conn.commit()



def create_claude_body(
    messages = [{"role": "user", "content": "Hello!"}],
    system = "You are an expert in finding the question corresponding to an SQL query",
    token_count=150,
    temp=0, 
    topP=1,
    topK=250, 
    stop_sequence=["Human"]):

    """
    Simple function for creating a body for Anthropic Claude models for the Messages API.
    https://docs.anthropic.com/claude/reference/messages_post
    """
    body = {
        "messages": messages,
        "max_tokens": token_count,
        "system":system,
        "temperature": temp,
        "anthropic_version":"",
        "top_k": topK,
        "top_p": topP,
        "stop_sequences": stop_sequence
    }

    return body

def get_claude_response(messages="", 
                        system = "",
                        token_count=250, 
                        temp=0,
                        topP=1, 
                        topK=250, 
                        stop_sequence=["\n\n"], 
                        model_id = "anthropic.claude-3-haiku-20240307-v1:0"):
    """
    Simple function for calling Claude via boto3 and the invoke_model API. 
    """
    body = create_claude_body(messages=messages, 
                              system=system,
                              token_count=token_count, 
                              temp=temp,
                              topP=topP, 
                              topK=topK, 
                              stop_sequence=stop_sequence)
    response = bedrock_rt.invoke_model(modelId=model_id, body=json.dumps(body))
    response = json.loads(response['body'].read().decode('utf-8'))

    return response

def get_metadata():

    #secret = get_secret()
    db_host = db_config["db_host"]
    db_name = db_config["db_name"]
    db_port = db_config["db_port"]
    db_user = db_config["user"]
    db_password = db_config["password"]
    

    # Connect to the PostgreSQL database
    conn = pymysql.connect(
        host=db_host,
        port=db_port,
        database=db_name,
        user=db_user,
        password=db_password
    )
    cursor = conn.cursor()
    metrics_context = None
    # Helper function to get column descriptions
    def get_column_description(table_name):
        column_des = ''
        query = """
        SELECT column_name, data_type, column_description 
        FROM columns_meta 
        WHERE source_table = %s
        """
        cursor.execute(query, (table_name,))
        columns = cursor.fetchall()

        for column_name, data_type, column_description in columns:
            column_des += f'''
            Column name: {column_name}\n
            Column data_type: {data_type}\n
            Column description: {column_description}\n\n
            '''
        return column_des

    # Fetching table metadata
    tables_metadata = {}
    cursor.execute("SELECT table_name, table_description FROM tables_meta")
    tables = cursor.fetchall()
    for table_name, table_description in tables:
        tables_metadata[table_name] = table_description

    # Building the context for tables and columns
    table_context = '''The tables in the database and their columns/attributes are described below:\n'''
    for table_name in list(tables_metadata.keys()):
        table_context += f'''
        Table '{table_name}' can be defined as follows:\n
        {tables_metadata[table_name]}\n\n
        It has the following columns with the following column name, data_type and description:\n
        {get_column_description(table_name)}\n\n
        '''

    
    # Fetching metric definitions
    metrics_metadata = []
    cursor.execute("SELECT metric, definition FROM metrics_def")
    metrics_metadata = cursor.fetchall()
    
    # Building the context for metrics
    metrics_context = '''
    The business uses several terminologies to describe the business metrics.
    Following are several metric acronyms, their meanings and a statement defining them 
    or how they can be calculated.\n\n
    '''

    for metric, definition in metrics_metadata:
        metrics_context += f'''
        The metric acronym {metric} is defined by {definition}\n
        '''
     # Closing the cursor and connection
    cursor.close()
    conn.close()

    return table_context, metrics_context


def get_examplePairs(examples_df, query_column_name, question_column_name):

    examples = f'''
    Following are example SQL query and question pairs.\n
    '''
    for index, row in examples_df.iterrows():
        #examples += f'''
        #SQL Query: {row["SQL Query"]}\n
        #<Question> {row["Question"]} </Question>\n\n
        #'''
        examples += f'''
        SQL Query: {row[query_column_name]}\n
        <Question> {row[question_column_name]} </Question>\n\n
        '''

    return examples


def gen_prompt(question, examples_df, query_column_name, question_column_name, metadata):

    prompt = f'''
        You are a SQL expert and for a given SQL query, you need to generate a textual description 
    for the SQL query. Encapsulate each of the descriptions within the tags <question_gen> and </question_gen>. 
    IMPORTANT: Provide a step by step description of how the SQL query is being executed and encapsulate 
    that within the tags <explanation> and </explanation>.\n\n
    '''
    examples = get_examplePairs(examples_df, query_column_name, question_column_name)

    if metadata:
        metrics_def, meta_def = get_metadata()
        prompt += f'''
        {meta_def}
        \n
        {metrics_def}
        \n
        {examples}
    
        Generate the question corresponding to the following SQL query:
        query: {question}
        <question_gen> 
    
        '''
    else:
        prompt += f'''
        {examples}
    
        Generate the question corresponding to the following SQL query:
        query: {question}
        <question_gen> 
    
        '''
    return prompt

def getmultitagtext(Inp_STR, tag="question_gen"):

    #tag = "Question"

    matches = re.findall(r"<"+tag+">(.*?)</"+tag+">", Inp_STR, flags=re.DOTALL)
    return matches

def gen_similar(question, modelID):

    print("Original Question:", question)

    prompt = f'''
    For the below english question describing an SQL query, generate five semantically similar question statements encapsulated within the tags <Question> and </Question>.\n\n
    
    {question}
    '''
    
    results = []
    results.append(question)
    msg = [{"role":"user", "content":prompt}]
    text_resp = get_claude_response(
        messages=msg,
        token_count=100000,
        temp=0,
        topP=1,
        topK=0,
        stop_sequence=["Human: "],
        model_id = modelID
    )
    print("generating five semantic questions: ", text_resp)
    five_res = getmultitagtext(text_resp['content'][0]['text'])
    results.extend(five_res)

    return results

def gen_similarSQL(query, model_id):

    metrics_def, meta_def = get_metadata()

    prompt = f'''
    Given the following description of the tables, columns and metric information,

    {meta_def}
    \n
    {metrics_def}
    \n
    
    For the below SQL query, generate an exactly same SQL query by only changing the values. Do not change the 
    table names and column names. Finally, encapsulate the generated SQL query within the tags <SQL></SQL>.\n\n

    {query}
    '''

    msg = [{"role":"user", "content":prompt}]
    text_resp = get_claude_response(
        messages=msg,
        token_count=100000,
        temp=0,
        topP=1,
        topK=0,
        stop_sequence=["Human: "],
        model_id = model_id
    )
    
    res = getmultitagtext(text_resp['content'][0]['text'], "SQL")

    return res
    
def get_question(query, examples_df, model_id, query_column_name, question_column_name, metadata=False):
    
    content = gen_prompt(query, examples_df, query_column_name, question_column_name, metadata)
    prompt = [{"role":"user", "content":content}]
    text_resp = get_claude_response(
        messages=prompt,
        token_count=100000,
        temp=0,
        topP=1,
        topK=0,
        stop_sequence=["Human: "],
        model_id = model_id
        )
    #print("LLM response:\n ",text_resp)
    result = getmultitagtext(text_resp['content'][0]['text'], "question_gen")
    explain_result = getmultitagtext(text_resp['content'][0]['text'], "explanation")
    
    return explain_result, result

def get_embeddings(text):

    # Define prompt and model parameters
    prompt_data = text
    
    body = json.dumps({
        "texts": [prompt_data],
        "input_type": "search_document"
    })

    model_id = 'cohere.embed-english-v3'
    accept = "*/*" #'application/json' 
    content_type = 'application/json'

    # Invoke model 
    response = bedrock_rt.invoke_model(
        body=body,
        modelId=model_id, 
        accept=accept, 
        contentType=content_type
    )

    # Print response
    response_body = json.loads(response['body'].read())
    embedding = response_body.get('embeddings')[0]

    return np.array(embedding)

def get_multiembeddings(questions):
    
    body = json.dumps({
        "texts": questions,
        "input_type": "search_document"
    })

    model_id = 'cohere.embed-english-v3'
    accept = "*/*" #'application/json' 
    content_type = 'application/json'

    # Invoke model 
    response = bedrock_rt.invoke_model(
        body=body,
        modelId=model_id, 
        accept=accept, 
        contentType=content_type
    )

    # Print response
    response_body = json.loads(response['body'].read())
    embeddings = response_body.get('embeddings')

    return embeddings

def main():

    # metadata_filename = "SQL2txt_Golden_dataset.xlsx"
    examples_filename = "golden data Question__Query pair.xlsx"

    query_column_name = "SQL Query" 
    question_column_name = "Question" 

    model_id = "anthropic.claude-3-haiku-20240307-v1:0"

    queries_df = pd.read_excel(examples_filename)
    queries_list = queries_df['SQL Query'].dropna().tolist()

    
    # Reading metadata and examples
    data = pd.ExcelFile(examples_filename)
    sheet_name = data.sheet_names[0]
    all_examples = data.parse(sheet_name)
    
    np.random.seed(4567)
    msk = np.random.rand(len(all_examples)) < 0.2
    examples_df = all_examples[msk]

    for sql_query in queries_list:
        # Generate question
        explanation, gen_question = get_question(sql_query, examples_df, model_id, query_column_name, question_column_name)

        results = gen_similar(gen_question[0], model_id)
        
        # Generate similar SQL query
        simquery = gen_similarSQL(sql_query, model_id)
        _, simquestion = get_question(simquery[0], examples_df, model_id, query_column_name, question_column_name)
        emb_simquestion = get_embeddings(simquestion[0])
        
        # Generate embeddings for similar questions
        embeddings = get_multiembeddings(results)
        
        questions = []
        for ques, emb_question in zip(results, embeddings):
            conf = np.dot(emb_question, emb_simquestion) / (norm(emb_question) * norm(emb_simquestion))
            questions.append({
                "question": ques,
                "confidence": conf
            })
        # Sort by confidence score to get the highest one
        questions.sort(key=lambda x: x["confidence"], reverse=True)
        
        # Store only the highest embedding in JSON
        highest_confidence_question = questions[0]
        highest_embedding = embeddings[results.index(highest_confidence_question["question"])]
        generated_question =[ques["question"] for ques in questions]
        confidence_scores = [ques["confidence"] for ques in questions]
        
        insert_query = sql.SQL("""
        INSERT INTO {table} ({sql_query}, {explanation}, {generated_question}, {embedded_questions}, {confidence_scores})
        VALUES (%s, %s, %s, %s, %s)
    """).format(
        table=sql.Identifier(table_name),  
        sql_query=sql.Identifier('sql_query'),
        explanation=sql.Identifier('explanation'),
        generated_question=sql.Identifier('generated_question'),
        embedded_questions=sql.Identifier('embedded_questions'),
        confidence_scores=sql.Identifier('confidence_scores')
    )
        
        cursor.execute(insert_query, (sql_query, explanation, generated_question, highest_embedding, confidence_scores))


        conn.commit()

    cursor.close()
    conn.close()
    print("Stored in DB successfully")
if __name__ == "__main__":  
    main()