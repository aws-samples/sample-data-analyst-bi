import boto3
import json
import numpy as np
from numpy.linalg import norm
from botocore.config import Config
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values
import os
import re
import logging

# Set up logging
logger = logging.getLogger(__name__)

my_config = Config(
    signature_version = 'v4',
    retries = {
        'max_attempts': 3,
        'mode': 'standard'
    }
)

vector_table = "examples"

def get_bedrock_client_for_model(model_id, region=None):
    """Get a Bedrock client with the specified region for the model"""
    from scripts.query_db.config import AWS_REGION
    
    # Use provided region or fall back to default
    client_region = region or AWS_REGION
    
    return boto3.client("bedrock-runtime", region_name=client_region, config=my_config)

# For backward compatibility, create a default client
bedrock_rt = get_bedrock_client_for_model("default")

def create_cache_table_if_not_exists(conn):
    """
    Create the cache table if it doesn't exist
    """
    try:
        with conn.cursor() as cur:
            # First check if the table exists
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = %s
                );
            """, (vector_table,))
            
            table_exists = cur.fetchone()[0]
            
            if not table_exists:
                logger.info("Cache table '%s' does not exist, creating it...", vector_table)
                
                # Create the pgvector extension if it doesn't exist
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                
                # Create the table with proper schema
                # Note: Adjust vector dimension (1024) based on your embedding model
                # Cohere multilingual v3 uses 1024 dimensions
                create_table_sql = f"""
                    CREATE TABLE {vector_table} (
                        id SERIAL PRIMARY KEY,
                        query TEXT NOT NULL,
                        question TEXT NOT NULL,
                        explanation TEXT,
                        gen_question TEXT,
                        question_embedding vector(1024),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """
                cur.execute(create_table_sql)
                
                # Create an index on the vector column for faster similarity searches
                cur.execute(f"""
                    CREATE INDEX ON {vector_table} 
                    USING ivfflat (question_embedding vector_cosine_ops)
                    WITH (lists = 100);
                """)
                
                conn.commit()
                logger.info("Successfully created cache table '%s' with vector index", vector_table)
            else:
                logger.debug("Cache table '%s' already exists", vector_table)
                
    except Exception as e:
        logger.error("Error creating cache table: %s", e, exc_info=True)
        conn.rollback()
        raise

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
                        model_id = "anthropic.claude-3-haiku-20240307-v1:0",
                        region=None):
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
    # Use model-specific client
    client = get_bedrock_client_for_model(model_id, region=region)
    response = client.invoke_model(modelId=model_id, body=json.dumps(body))
    response = json.loads(response['body'].read().decode('utf-8'))

    return response
    
def get_embedding(text, emb_model_id, region=None):
    """
    Creates the embedding of the nlq/text question
    """
    body = json.dumps({"inputText": text, "embeddingTypes": ["float"]})

    # Use model-specific client
    client = get_bedrock_client_for_model(emb_model_id, region=region)
    response = client.invoke_model(
        body=body,
        modelId=emb_model_id,
        accept="application/json",
        contentType="application/json",
    )

    response_body = json.loads(response["body"].read())
    return response_body["embedding"]


def getmultitagtext(Inp_STR, tag="question_gen"):

    #tag = "Question"

    matches = re.findall(r"<"+tag+">(.*?)</"+tag+">", Inp_STR, flags=re.DOTALL)
    return matches


def gen_prompt(query, question):
    
    prompt_temp = f'''
        You are an expert SQL analyst.  For a given SQL query inside <SQL> tags, Provide a step by step description of how the SQL query is being executed and encapsulate 
    that within the tags <explanation> and </explanation>.

    For the given text question inside <question> tags ,you need to write the question in a different way maintaining the semantics and the intent
    and return within the tags <question_gen> and </question_gen>. 

    <SQL>
    {query}
    </SQL>

    <question>
    {question}
    </question>
    '''
    prompt = prompt_temp.format(query=query, question=question)
    return prompt



def get_expl_question(query, question, expl_model_id, region=None):
    
    content = gen_prompt(query, question)
    prompt = [{"role":"user", "content":content}]
    text_resp = get_claude_response(
        messages=prompt,
        token_count=100000,
        temp=0,
        topP=1,
        topK=0,
        stop_sequence=["Human: "],
        model_id=expl_model_id,
        region=region
        )
    logger.debug("LLM response: %s", text_resp)
    question_variant = getmultitagtext(text_resp['content'][0]['text'], "question_gen")
    explain_result = getmultitagtext(text_resp['content'][0]['text'], "explanation")
    
    return explain_result, question_variant


def insert_data_to_postgres(conn, ingest_data):
    """
    Creates the connection to the vector database and ingests the data
    """
    with conn.cursor() as cur:
        data = [
            (ingest_data["queries"], ingest_data["question"], ingest_data["explanation"], ingest_data["gen_question"], ingest_data["question_embeddings"])
        ]
        execute_values(
            cur,
            f"""
            INSERT INTO {vector_table} 
            (query, question, explanation, gen_question, question_embedding)
            VALUES %s
        """,
            data,
        )

        conn.commit()
        logger.info("Inserted %d rows into the database.", len(data))
        message = f"Inserted {len(data)} rows into the database."
        return message

def write_to_cache(expl_model_id, emb_model_id, question_query_map, db_params, query_key_name="queries",
                             question_key_name="question", expl_model_region=None, emb_model_region=None):
    """
    Ingests the fewshot examples in the vector database
    """

    query = question_query_map[query_key_name]
    question = question_query_map[question_key_name]

    explanation, question_variant = get_expl_question(query, question, expl_model_id, region=expl_model_region)
    logger.debug("explanation: %s", explanation)
    logger.debug("question_variant: %s", question_variant)
    question_embeddings = get_embedding(question, emb_model_id, region=emb_model_region)
    ingest_data = {"queries":query, "question": question, "explanation": explanation, "gen_question":question_variant, "question_embeddings":question_embeddings}
    logger.debug("db_params configured for connection")
    try:
        logger.info("Connecting to the PostgreSQL database...")
        conn = psycopg2.connect(**db_params)
        logger.info("Connection established successfully!")

        # Ensure table exists before inserting
        create_cache_table_if_not_exists(conn)

        message = insert_data_to_postgres(conn, ingest_data)
        status_code = 200
    except psycopg2.Error as error:
        logger.error("Error in PostgreSQL operation: %s", error)
        message = f"Error in data ingestion operation: {error}"
        status_code = 500
    finally:
        if conn:
            conn.close()
            logger.info("PostgreSQL connection is closed")
        return message, status_code

def similarity_search(conn, query_embedding, top_k) -> list[tuple]:
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT query, question, explanation, gen_question, 1 - (question_embedding <=> %s::vector) AS similarity
                FROM {vector_table}
                ORDER BY question_embedding <=> %s::vector
                LIMIT %s;
                """,
                (query_embedding, query_embedding, top_k),
            )

            results = cur.fetchall()
            return results
    except Exception as e:
        logger.error("Error in similarity_search: %s", e, exc_info=True)
        return []

def get_embedding(text, embedding_model_id, region=None):
    # Use model-specific client
    bedrock = get_bedrock_client_for_model(embedding_model_id, region=region)

    if 'cohere' in embedding_model_id:
        body = json.dumps({
        "texts": [text],
        "input_type": "search_query",
        "truncate": "END",
        "embedding_types": ["float"]
    })
    else:
        body = json.dumps({
            "inputText": text,
            "embeddingTypes": ["float"]
        })

    logger.debug("Embedding Model ID: %s", embedding_model_id)

    response = bedrock.invoke_model(
        body=body,
        modelId=embedding_model_id,
        accept='application/json',
        contentType='application/json'
    )
    
    response_body = json.loads(response['body'].read())
    if 'cohere' in embedding_model_id:
        return response_body['embeddings']['float'][0]
    
    return response_body['embedding']

def get_cached_query(text_query: str, embedding_model_id: str, cache_thresh: float, db_params:dict, embedding_model_region=None) -> list[str]:
        query = None
        # db_params = {
        #     "host": os.environ.get("DB_HOST"),
        #     "port": os.environ.get("DB_PORT"),
        #     "database": os.environ.get("DB_NAME"),
        #     "user": os.environ.get("DB_USER"),
        #     "password":'BlsAmz#20',
        # }
        logger.debug("vector_db_params configured")
        
        try:
            conn = psycopg2.connect(**db_params)
            conn.autocommit = True
            
            # Ensure table exists before querying
            create_cache_table_if_not_exists(conn)
            
        except Exception as e:
            logger.error("get_cached queries: Failed to establish connection: %s", e)
            return None
        
        embeddings = get_embedding(text_query, embedding_model_id, region=embedding_model_region)
        #print("embeddings", embeddings)
        similarity_examples = similarity_search(conn, embeddings, 1)
        logger.debug("similarity_examples: %s", similarity_examples)
        for query, question, expl, gen_question,  similarity in similarity_examples:
            logger.debug('get_cached_query: Evaluating example: query=%s, question=%s, expl=%s, gen_question=%s, similarity=%s', 
                        query, question, expl, gen_question, similarity)
            if similarity >= cache_thresh:
                return query
            else:
                return None