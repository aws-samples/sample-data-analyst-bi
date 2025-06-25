import boto3
import pandas as pd
import numpy as np
import json
import psycopg2
from config import vector_db_config

def add_vector_extension(cur):
    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        print("Vector extension added successfully.")
    except psycopg2.Error as e:
        print(f"Could not add vector extension: {e}")

def create_vector_cache(cur):
    """
    Creates the table in the vector database to store the data
    """
    try:
        print(f"Table Name: examples")
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS examples (
                id SERIAL PRIMARY KEY,
                query TEXT NOT NULL,
                question TEXT NOT NULL,
                explanation TEXT NOT NULL,
                gen_question TEXT NOT NULL,
                question_embedding vector(1024)
            );
            CREATE INDEX IF NOT EXISTS question_embedding_idx
            ON examples
            USING ivfflat (question_embedding vector_cosine_ops)
            WITH (lists = 100);
        """)
        print(f"Table examples created successfully with vector index.")
    except psycopg2.Error as e:
        print(f"Could not create table: {e}")

def create_vector_db():


    try:
        print("Connecting to the PostgreSQL database...")
        conn = psycopg2.connect(**vector_db_config)
        print("Connection established successfully!")
    
        with conn.cursor() as cur:
            add_vector_extension(cur)
            create_vector_cache(cur)
            conn.commit()
    except psycopg2.Error as error:
            print(f"Error in PostgreSQL operation: {error}")
            message = f"Error in data ingestion operation: {error}"
            status_code = 500

if __name__ == "__main__":  
    create_vector_db()