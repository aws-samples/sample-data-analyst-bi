
import boto3
import pandas as pd
import numpy as np
import json
import psycopg2
import os
from psycopg2.extras import execute_values
from SQL2Text import get_question
from config import vector_db_config, vector_table_name, fshot_example_filename, explnation_modelid, region_name


bedrock = boto3.client(service_name="bedrock-runtime", region_name=region_name)


def get_embedding(text):
    """
    Creates the embedding of the nlq/text question
    """
    body = json.dumps({"inputText": text, "embeddingTypes": ["float"]})

    response = bedrock.invoke_model(
        body=body,
        modelId="amazon.titan-embed-text-v2:0",
        accept="application/json",
        contentType="application/json",
    )

    response_body = json.loads(response["body"].read())
    return response_body["embedding"]


def insert_data_to_postgres(conn, df):
    """
    Creates the connection to the vector database and ingests the data
    """
    with conn.cursor() as cur:
        data = [
            (row["queries"], row["question"], row["explanation"], row["gen_question"], row["question_embeddings"])
            for _, row in df.iterrows()
        ]
        execute_values(
            cur,
            f"""
            INSERT INTO {vector_table_name} 
            (query, question, explanation, gen_question, question_embedding)
            VALUES %s
        """,
            data,
        )

        conn.commit()
        print(f"Inserted {len(data)} rows into the database.")
        message = f"Inserted {len(data)} rows into the database."
        return message


def ingest_examples(model_id, examples_filename, db_params):
    """
    Ingests the fewshot examples in the vector database
    """
    examples = generate_sql_explanation(model_id, examples_filename)
    examples = examples.dropna()
    examples.columns = examples.columns.str.lower()
    examples["question_embeddings"] = examples["question"].apply(get_embedding)
    print(examples.head(2))
    try:
        print("Connecting to the PostgreSQL database...")
        conn = psycopg2.connect(**db_params)
        print("Connection established successfully!")

        with conn.cursor() as cur:
            add_vector_extension(cur)
            create_table_fshot(cur)
            conn.commit()

        message = insert_data_to_postgres(conn, examples)
        status_code = 200
    except psycopg2.Error as error:
        print(f"Error in PostgreSQL operation: {error}")
        message = f"Error in data ingestion operation: {error}"
        status_code = 500
    finally:
        if conn:
            conn.close()
            print("PostgreSQL connection is closed")
    

def generate_sql_explanation(model_id, examples_filename, query_column_name="queries",
                             question_column_name="question"):
    """
    Generates the explanation for the SQL and also a sematically similar NLQ 
    """
    np.random.seed(4567)
    explanation_list = []
    gen_question_list = []
    queries_df = pd.read_excel(examples_filename)
    queries_list = queries_df[query_column_name].dropna().tolist()

    data = pd.ExcelFile(examples_filename)
    sheet_name = data.sheet_names[0]
    all_examples = data.parse(sheet_name)
    msk = np.random.rand(len(all_examples)) < 0.1
    examples_df = all_examples[msk]
    for index, row in queries_df.iterrows():
        question = row['question']
        sql = row['queries']
        # Generate the explanation and the question
        explanation, gen_question = get_question(sql, examples_df, model_id,
                                                 query_column_name, question_column_name)
        explanation_list.extend(explanation)
        gen_question_list.extend(gen_question)

    queries_df['explanation'] = explanation_list
    queries_df['gen_question'] = gen_question_list

    return queries_df

def main():

    try:
        example_filepath = os.path.join("fshot_data", fshot_example_filename)
        ingest_examples(explnation_modelid, example_filepath, vector_db_config)
    except Exception as e:
        print(f"Error in ingesting examples to vector database: {str(e)}")
        status_code = 500

if __name__ == "__main__":  
    main()