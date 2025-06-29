import os
import sys
project_root = '/home/sagemaker-user/data_analyst_bot/da_refactor'
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pandas as pd
from scripts.query_db.prompt_config_clv2 import query_text_tab_temp, query_text_tab_ex_temp
from scripts.query_db.prompt_config_clv3 import query_text_tab_tempv3, query_text_tab_ex_temp
from scripts.query_db.config import DATA_DIR, MODEL_CONF, schema_file, META_DIR
from scripts.query_db.config import table_meta_file, token_interpretation, col_meta_file, metric_meta_file
from scripts.utils import load_data, extract_data
from scripts.run_llm_inferencev2 import BedrockTextGenerator

base_dir = os.path.dirname(__file__)



"""This class contains the functions to generate fewshot prompt and to classify a question into categories by using an LLM
"""
class FewShotTabBedrock():
    _allowed_model_ids = MODEL_CONF.keys()
    
    def __init__(self, modelid, model_region: str = None):
        if modelid not in self._allowed_model_ids:
            raise ValueError(f'Error: model_id should be chosen from {self._allowed_model_ids}')
        self.modelid = modelid
        self.model_region = model_region
        self.model_params = MODEL_CONF[modelid]

    def create_schema_meta(self, schema, tab_meta, col_meta, metric_meta=None):
        """This function is used to add the schema tables and columns in a specified format to the prompt

        Args:
            schema(DataFrame): the tables and columns
            tab_meta(DataFrame): The table names and their glossary/metadata
            col_meta(DataFrame): The column names and their glossary/metadata
            metric_meta(DataFrame): Metadata containing metric names and descriptions
        Returns: The schema in string format
        """
        schema_str = """"""
        cols_meta = col_meta.col_name.values.tolist()
        schema = schema[schema['col_name'].isin(cols_meta)]
        
        # Add metrics section if metric_meta is provided
        if metric_meta is not None:
            metrics_str = "<metrics>\n"
            metrics_str += "Metrics:\n"
            
            for i, row in metric_meta.iterrows():
                metric_name = row["Metric Name"]
                metric_desc = row["Description"]
                metrics_str += "{}.Name: {}\nDescription: {}\n".format(i+1, metric_name, metric_desc)
            
            metrics_str += "</metrics>\n"
            schema_str += metrics_str
       
        tables = schema['table_name'].unique().tolist()
        for i, tab in enumerate(tables):
            col_str = """"""
            cols = schema[schema['table_name'] == tab]['col_name'].tolist()
            tab_col = '<table{i}>\n{data}</table{i}>\n'
            if tab_meta.shape[0] > 0:
                tab_desc = tab_meta[tab_meta.table_name == tab]['description'].tolist()[0]
                #print('tab_desc',tab_desc)
            else:
                tab_desc = None 
            table_meta_str = 'TableName: {}\n'.format(tab) + 'Description: {}\nColumnNames:\n'.format(tab_desc)
            for j, col in enumerate(cols):
                if col_meta.shape[0] > 0:
                    col_desc = col_meta[col_meta.col_name == col]['description'].tolist()[0]
                    #print('col_desc',col_desc)
                else:
                    col_desc = None
                col_meta_str = '{j}.Name:{col}\nDescription: {desc}\n'.format(j=j+1,col=col,desc=col_desc)
                col_str += col_meta_str       
            data_str = table_meta_str + col_str
            schema_str += tab_col.format(i=i+1, data=data_str)
        return schema_str

    def create_prompt(self) -> str:
        """This function is to be used to generate fewshot prompt 
            
        """
        fshot_prompt = ''
        error_msg = ''
        try:
            table_meta_path = os.path.join(META_DIR, table_meta_file)
            col_meta_path = os.path.join(META_DIR, col_meta_file)
            metric_meta_path = os.path.join(META_DIR, metric_meta_file)
            print('table_meta_path', table_meta_path)
            if os.path.exists(table_meta_path):
                tab_meta = load_data(META_DIR, table_meta_file)
                print('tab_meta shape', tab_meta.shape)
            else:
                tab_meta = pd.DataFrame()
            if os.path.exists(col_meta_path):
                col_meta = load_data(META_DIR, col_meta_file)
            else:
                col_meta = pd.DataFrame()
            if os.path.exists(metric_meta_path):
                metric_meta = load_data(META_DIR, metric_meta_path)
            else:
                metric_meta = pd.DataFrame()
                
            schema = load_data(DATA_DIR, schema_file)
            schema_meta = self.create_schema_meta(schema, tab_meta, col_meta, metric_meta)
            print('schema_meta', schema_meta)
            if 'claude-3' in self.modelid or 'nova' in self.modelid or 'llama' in self.modelid:
                fshot_prompt = query_text_tab_tempv3.format(schema_meta=schema_meta, token_intp=token_interpretation)
            #print('fshot_prompt',fshot_prompt)
        except Exception as e:
            error_msg = str(e)  + 'Module:{}'.format('FewShotTabBedrock')
            print('error_msg', error_msg)
        return fshot_prompt, error_msg

    def generate_tables(self, messages:list) -> str:
        """This function is to be used to invoke an LLM with a prompt to get relevant tables related to a text 
        query. These tables will help to identify whether a persona is eligible to access the tables
        Args:
            messages(list): the list of content passed by user and responses from bot
        Returns: the generated tables and error message if any
        """
        tab_gen = None
        prompt, error_msg = self.create_prompt()
        if prompt != '':
        #print('prompt table', prompt)
            tab_generator = BedrockTextGenerator(self.modelid, self.model_params, region=self.model_region)
            text_resp, error_msg = tab_generator.generate(input_text=messages, prompt=prompt)
            if error_msg == '':
                print('table_extraction_resp', text_resp)
                tab_gen = extract_data(text_resp)
        return tab_gen, error_msg