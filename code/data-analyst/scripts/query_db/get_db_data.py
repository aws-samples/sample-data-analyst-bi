import os
import sys
project_root = '/home/sagemaker-user/data_analyst_bot/da_refactor'
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import re
import pandas as pd
import datetime
import signal
import time
import sqlite3
from scripts.query_db.config import DATA_DIR, text_sql_example_file, MODEL_CONF, domain_vars_map
from scripts.query_db.config import n_SHOTS, index_model, schema_file, DB_PATH, index_type
from scripts.query_db.config import num_record_thresh, exec_time_thresh, emb_model
from scripts.utils import load_data, extract_data, log_error
from scripts.run_llm_inferencev2 import BedrockTextGenerator, SQLCoderGenerator
from scripts.query_db.prompt_generator import PromptGenerator
from func_timeout import func_timeout, FunctionTimedOut

base_dir = os.path.dirname(__file__)
root_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))



"""This class contains the functions to generate fewshot prompt for SQL generation task and to prompt a LLM to generate SQL
"""

class SQLGenerator():
    _allowed_model_ids = MODEL_CONF.keys()
    
    def __init__(self, modelid: str, prompt_type: str):
        print('modelid', modelid)
        if modelid not in self._allowed_model_ids:
            raise ValueError(f'Error: model_id should be chosen from {self._allowed_model_ids}')
        self.modelid = modelid
        self.model_params = MODEL_CONF[modelid]
        self.prompt_type = prompt_type

    def create_prompt(self, question:str, query_tabs:list) -> str:
        """This function is to be used to generate fewshot prompt for SQL generation task by invoking the 
        PromptGenerator class in prompt_generator.py 

        Args:
            question (str): text query
            query_tabs (list): the list of tables retrieved for the specific question asked by the user
        Returns: Prompt
        """
        if self.prompt_type in ['fewshot','fewshot_cot']:
            df_prompt_ex = load_data(DATA_DIR, text_sql_example_file)
            schema = load_data(DATA_DIR, schema_file)
            prompt_gen = PromptGenerator(emb_model=emb_model, prompt_type=self.prompt_type, n_SHOTS=n_SHOTS, 
                                         index_model= index_model, index_type=index_type, gen_llm=self.modelid)
            prompt = prompt_gen.create_fewshot_prompt(schema, question, query_tabs, df_prompt_ex)
            #print('prompt',prompt)
        elif self.prompt_type == 'zeroshot':
            schema = load_data(DATA_DIR, schema_file)
            prompt_gen = PromptGenerator(emb_model=None, prompt_type=self.prompt_type, n_SHOTS=None, 
                                         index_model= None, index_type=None, gen_llm=self.modelid)
            prompt = prompt_gen.create_zeroshot_prompt(schema, question, query_tabs)
        return prompt

    def generate_sql(self, messages: list, question:str, query_tabs:list) -> str:
        """This function is to be used to invoke the LLMs to generate SQL

        Args:
            messages(list): the list of content passed by user and responses from bot
            question (str): the question from the user
            query_tabs (list): the list of tables retrieved for the specific question asked by the user
        Returns: list of sql and error messages
        """
        prompt = self.create_prompt(question, query_tabs)
        error_msg = ''
        sql = ''
        try:
            if 'claude' in self.modelid or 'nova' in self.modelid or 'llama' in self.modelid:
                sql_generator = BedrockTextGenerator(self.modelid, self.model_params)
                print('messages get db', messages)
                text_resp, error_msg = sql_generator.generate(input_text=messages, prompt=prompt)
                print('sql_text_resp', text_resp)
                if error_msg == '':
                    sql = extract_data(text_resp, tag1='<sql>', tag2='</sql>')
                    print('generated sql', sql)
            elif 'sqlcoder' in self.modelid:
                sql_generator = SQLCoderGenerator(self.modelid, self.model_params)
                sql = sql_generator.generate(prompt)
        except Exception as e:
            error_msg = str(e)
        return [sql, error_msg]