from abc import ABC, abstractmethod
import logging
import json
import os
import pandas as pd
import boto3
from datetime import datetime
import psycopg2
from typing import List, Optional
from scripts.sagemaker_llm import SageMakerLLM
from scripts.bedrock_llm import BedrockLLM
from scripts.utils import init_bedrock_llm, get_embedding, s3_key_exists
from scripts.config import LLM_CONF, AWS_REGION, AOSS_RELEVANCE_THRESHOLD, CACHE_THRESHOLD
from scripts.prompts import (
    BEDROCK_SYS_PROMPT,
    LLM_ZS_PROMPTS,
    LLM_FS_PROMPTS,
    LLM_PROMPTS_FINAL,
    FS_EXAMPLE_STRUCTURE,
    BEDROCK_ZS_METADATA_SQL_PROMPT,
    BEDROCK_FS_METADATA_SQL_PROMPT,
)
from scripts.sql.executor import get_database_helper
from scripts.filter_tables import filter_tables, create_schema_meta, filter_table_info

logger = logging.getLogger(__name__)

os.environ["AWS_DEFAULT_REGION"] = AWS_REGION


class SQLGenerator(ABC):
    _allowed_approaches = ("zero_shot", "few_shot")

    def __init__(
        self,
        model_id: str,
        approach: str,
        database: str,
        db_conn_conf: dict[str, str],
        schema_file: str,
        model_params: str = None,
    ) -> None:
        super().__init__()
        if approach not in self._allowed_approaches:
            raise ValueError(
                f"Error: approach should be chosen from {self._allowed_approaches}"
            )
        self.model_id = model_id
        self.approach = approach
        self.database = database
        self.db_conn_conf = db_conn_conf
        self.schema_file = schema_file
        self.model_params = model_params
        
    def similarity_search(self, conn, query_embedding, top_k) -> list[tuple]:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT query, question, explanation, gen_question, 1 - (question_embedding <=> %s::vector) AS similarity
                    FROM examplesv2
                    ORDER BY question_embedding <=> %s::vector
                    LIMIT %s;
                    """,
                    (query_embedding, query_embedding, top_k),
                )

                results = cur.fetchall()
                return results
        except Exception as e:
            logging.error(f"Error in similarity_search: {e}", exc_info=True)
            return []
    def get_fewshot_examples(self, text_query: str, embedding_model_id: str) -> list[str]:
        db_params = {
            "host": os.environ.get("POSTGRES_ENDPOINT"),
            "port": os.environ.get("POSTGRES_PORT"),
            "database": os.environ.get("POSTGRES_DB"),
            "user": os.environ.get("POSTGRES_USERNAME"),
            "password": os.environ.get("POSTGRES_PASSWORD"),
        
        }
        self.conn = psycopg2.connect(**db_params)
        try:
            self.conn.autocommit = True
        except:
            print("get_fewshot_examples: Failed to establish connection")
        embeddings = get_embedding(text_query, embedding_model_id)
        #print("embedding inside fewshot", embeddings)
        similarity_examples = self.similarity_search(self.conn, embeddings, self.k)
        print("similarity_examples inside fewshot", similarity_examples)
        examples = []
        for query, question, expl, gen_question,  similarity in similarity_examples:
            print('get_fewshot_examples: Evaluating example:', query, question, expl, gen_question, similarity)
            if similarity >= AOSS_RELEVANCE_THRESHOLD:
                examples.append(
                    FS_EXAMPLE_STRUCTURE.format(question=question, sql=query, expl=expl, gen_q=gen_question)
                )
        return examples

    

    @abstractmethod
    def generate_zeroshot(self, text_query: str) -> str:
        pass

    @abstractmethod
    def generate_fewshot(self, text_query: str, embedding_model_id: str) -> str:
        pass


class SQLGeneratorBedrock(SQLGenerator):
    _allowed_model_ids = LLM_CONF.keys()

    def __init__(
        self,
        model_id: str,
        approach: str,
        database: str,
        db_conn_conf: dict[str, str],
        schema_file: str,
        aoss_host: str = None,
        aoss_index: str = None,
        model_params: dict[str, any] = None,
        k: int = 5,
    ) -> None:
        if model_id not in self._allowed_model_ids:
            raise ValueError(
                f"Error: model_id should be chosen from {self._allowed_model_ids}"
            )
        super().__init__(
            model_id, approach, database, db_conn_conf, schema_file, model_params
        )
        if model_id.startswith('ic-'):
            self._llm = SageMakerLLM(endpoint_name='data-analyst-endpoint-1', inference_component_name=model_id, region_name=AWS_REGION)
        else:
            self._llm = BedrockLLM(model_id=model_id, region_name=AWS_REGION)
        self._db_helper = get_database_helper(
            database,
            db_conn_conf,
            None,
            model_id,
            model_params,
            rectification_attempt=3,
            schema_file=schema_file,
        )
        self.aoss_host = aoss_host
        self.aoss_index = aoss_index
        self.k = k


    def get_cached_query(self, text_query: str, embedding_model_id: str) -> list[str]:
        query = None
        db_params = {
            "host": os.environ.get("DB_HOST"),
            "port": os.environ.get("DB_PORT"),
            "database": os.environ.get("DB_NAME"),
            "user": os.environ.get("DB_USER"),
            "password":os.environ.get("DB_PASSWORD"),
        }
        self.conn = psycopg2.connect(**db_params)
        try:
            self.conn.autocommit = True
        except:
            print("get_cached queries: Failed to establish connection")
            return None
        
        embeddings = get_embedding(text_query, embedding_model_id)
        #print("embeddings", embeddings)
        similarity_examples = self.similarity_search(self.conn, embeddings, 1)
        print("similarity_examples", similarity_examples)
        for query, question, expl, gen_question,  similarity in similarity_examples:
            print('get_cached_query: Evaluating example:', query, question, expl, gen_question, similarity)
            if similarity >= CACHE_THRESHOLD:
                return query
            else:
                return None

    def generate_zeroshot(
        self,
        text_query: str,
        examples: Optional[List[str]] = None,
        table_meta: Optional[str] = None,
        column_meta: Optional[str] = None,
        metric_meta: Optional[str] = None,
        table_access: Optional[str] = None,
        is_meta: Optional[bool] = False,
        s3_bucket_name: Optional[str] = None,
        embedding_model_id = None
    ) -> str:
        start_time = datetime.now()
        schema_info, foreign_key_str, distinct_values = self._db_helper.get_schema_info()
        if not isinstance(schema_info, str):
            print('schema_info is not a str')
            print('is_meta:', is_meta)
            if is_meta:
                if s3_key_exists(s3_bucket_name, table_meta) and s3_key_exists(
                    s3_bucket_name, column_meta
                ):
                    table_meta = pd.read_excel(f"s3://{s3_bucket_name}/{table_meta}")
                    column_meta = pd.read_excel(f"s3://{s3_bucket_name}/{column_meta}")
                    metric_meta = pd.read_excel(f"s3://{s3_bucket_name}/{metric_meta}")
                else:
                    table_meta = None
                    column_meta = None
                    metric_meta = None
                    is_meta = False
                schema_meta = create_schema_meta(
                    schema_info, table_meta, column_meta, None, foreign_key_str, is_meta, distinct_values, metric_meta
                )
                if schema_meta is None:
                    schema_meta = json.dumps({"schema": schema_info.to_dict()})
                else:
                    LLM_ZS_PROMPTS.update(
                        {self.model_id: BEDROCK_ZS_METADATA_SQL_PROMPT}
                    )
            else:
                schema_meta = create_schema_meta(
                    schema_info, table_meta, column_meta, None, foreign_key_str, is_meta, distinct_values, metric_meta
                )
        else:
            schema_meta = schema_info
        if table_access:
            if s3_key_exists(s3_bucket_name, table_access):
                table_access = f"s3://{s3_bucket_name}/{table_access}"
            else:
                table_access = None
        message, tables_list = filter_tables(
            text_query, schema_meta, table_access, self.model_id
        )
        print("Filtered Tables:", tables_list)
        if message:
            return message, schema_info, foreign_key_str, schema_meta
        filtered_schema_meta = filter_table_info(schema_meta, tables_list)
        sys_prompt = BEDROCK_SYS_PROMPT.format(sql_database=self.database)
        sql_prompt = LLM_ZS_PROMPTS[self.model_id].format(
            schema=filtered_schema_meta, question=text_query
        )
        if self.model_id.startswith('ic-'):
            sql = self._llm(sql_prompt, system_prompt=sys_prompt)
        else:
            if "{sys_prompt}" in LLM_PROMPTS_FINAL[self.model_id]:
                final_prompt = LLM_PROMPTS_FINAL[self.model_id].format(
                    sys_prompt=sys_prompt, sql_prompt=sql_prompt
                )
            else:
                final_prompt = LLM_PROMPTS_FINAL[self.model_id].format(
                    sql_prompt=sql_prompt
                )
            sql = self._llm(final_prompt, system_prompt=sys_prompt)
        print('Response:', sql.replace("\n", ""))
        sql = (
            sql.split("<sql>")[1]
            .split("</sql>")[0]
        )
        return sql, schema_info, foreign_key_str, schema_meta

    def generate_fewshot(
        self,
        text_query: str,
        examples: Optional[List[str]] = None,
        table_meta: Optional[str] = None,
        column_meta: Optional[str] = None,
        metric_meta: Optional[str] = None,
        table_access: Optional[str] = None,
        is_meta: Optional[bool] = False,
        s3_bucket_name: Optional[str] = None,
        embedding_model_id: Optional[str] = None
    ) -> str:
        schema_info, foreign_key_str, distinct_values = self._db_helper.get_schema_info()
        if not isinstance(schema_info, str):
            if is_meta:
                print('Using metadata from s3.')
                if s3_key_exists(s3_bucket_name, table_meta) and \
                    s3_key_exists(s3_bucket_name, column_meta) and \
                    s3_key_exists(s3_bucket_name, metric_meta):
                    print('s3 keys for metadata exist.')
                    table_meta = pd.read_excel(f"s3://{s3_bucket_name}/{table_meta}")
                    column_meta = pd.read_excel(f"s3://{s3_bucket_name}/{column_meta}")
                    metric_meta = pd.read_excel(f"s3://{s3_bucket_name}/{metric_meta}")
                else:
                    print('s3 keys for metadata don\'t exist.')
                    table_meta = None
                    column_meta = None
                    is_meta = None
                schema_meta = create_schema_meta(
                    schema_info, table_meta, column_meta, None, foreign_key_str, is_meta, distinct_values, metric_meta
                )
                if schema_meta is None:
                    schema_meta = json.dumps({"schema": schema_info.to_dict()})
                else:
                    LLM_FS_PROMPTS.update(
                        {self.model_id: BEDROCK_FS_METADATA_SQL_PROMPT}
                    )
            else:
                schema_meta = create_schema_meta(
                    schema_info, table_meta, column_meta, None, foreign_key_str, is_meta, distinct_values, metric_meta
                )
        else:
            print('Metadata from s3 not provided.')
            schema_meta = schema_info
        if table_access:
            if s3_key_exists(s3_bucket_name, table_access):
                table_access = f"s3://{s3_bucket_name}/{table_access}"
            else:
                table_access = None
        message, tables_list = filter_tables(
            text_query, schema_meta, table_access, self.model_id
        )
        print("Schema Meta:", schema_meta)
        print("Filtered Tables ::", tables_list)
        if message:
            return message
        filtered_schema_meta = filter_table_info(schema_meta, tables_list)
        examples = self.get_fewshot_examples(text_query, embedding_model_id)
        print("examples retrieved:", examples)
        sys_prompt = BEDROCK_SYS_PROMPT.format(sql_database=self.database)
        sql_prompt = LLM_FS_PROMPTS[self.model_id].format(
            schema=filtered_schema_meta,
            examples="\n".join(examples),
            question=text_query,
        )
        if self.model_id.startswith('ic-'):
            sql = self._llm(sql_prompt, system_prompt=sys_prompt)
        else:
            if "{sys_prompt}" in LLM_PROMPTS_FINAL[self.model_id]:
                final_prompt = LLM_PROMPTS_FINAL[self.model_id].format(
                    sys_prompt=sys_prompt, sql_prompt=sql_prompt
                )
            else:
                final_prompt = LLM_PROMPTS_FINAL[self.model_id].format(
                    sql_prompt=sql_prompt
                )
            sql = self._llm(final_prompt, system_prompt=sys_prompt)
        print('Response:', sql.replace("\n", ""))
        sql = (
            sql.split("<sql>")[1]
            .split("</sql>")[0]
        )
        return sql, schema_info, foreign_key_str, schema_meta


class SQLGeneratorHF(SQLGenerator):
    DEFAULT_MODEL = "hf_codellama"

    def __init__(
        self,
        model_id: str,
        approach: str,
        database: str,
        db_conn_conf: dict[str, str],
        schema_file: str,
        aoss_host: str = None,
        aoss_index: str = None,
        model_params: str = None,
        k: int = 5,
    ) -> None:
        super().__init__(
            model_id, approach, database, db_conn_conf, schema_file, model_params
        )
        self._db_helper = get_database_helper(
            database,
            db_conn_conf,
            None,
            model_id,
            model_params,
            schema_file=schema_file,
        )
        self.aoss_host = aoss_host
        self.aoss_host = aoss_host
        self.aoss_index = aoss_index
        self.k = k

    def invoke_sm_model_endpoint(self, prompt):
        runtime = boto3.Session().client("sagemaker-runtime")
        model_params = (
            LLM_CONF[self.__class__.DEFAULT_MODEL]
            if self.model_params is None
            else self.model_params
        )
        payload = {"inputs": prompt, "parameters": model_params}
        payload = json.dumps(payload, indent=2).encode("utf8")
        response = runtime.invoke_endpoint(
            EndpointName=self.model_id, ContentType="application/json", Body=payload
        )
        output = json.loads(response["Body"].read().decode())
        sql = output["generated_text"].strip()
        sql = sql.replace("```", "").replace(";;", ";")

        return sql

    def generate_zeroshot(self, text_query: str) -> str:
        runtime = boto3.Session().client("sagemaker-runtime")
        schema_info = self._db_helper.get_schema_info()
        sql_prompt = LLM_ZS_PROMPTS[self.__class__.DEFAULT_MODEL].format(
            sql_database=self.database,
            schema=schema_info,
            question=text_query,
            query="",
        )
        final_prompt = LLM_PROMPTS_FINAL[self.__class__.DEFAULT_MODEL].format(
            sql_prompt=sql_prompt
        )
        sql = self.invoke_sm_model_endpoint(final_prompt)

        return sql

    def generate_fewshot(self, text_query: str, embedding_model_id: str) -> str:
        schema_info = self._db_helper.get_schema_info()
        examples = self.get_fewshot_examples(text_query, embedding_model_id)
        sql_prompt = LLM_FS_PROMPTS[self.__class__.DEFAULT_MODEL].format(
            sql_database=self.database,
            schema=schema_info,
            examples="\n".join(examples),
            question=text_query,
        )
        final_prompt = LLM_PROMPTS_FINAL[self.__class__.DEFAULT_MODEL].format(
            sql_prompt=sql_prompt
        )

        sql = self.invoke_sm_model_endpoint(final_prompt)

        return sql
