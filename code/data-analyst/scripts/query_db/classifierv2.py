import os
import sys
project_root = '/home/sagemaker-user/data_analyst_bot/da_refactor'
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# One-time path setup at the start of each module
#current_file = os.path.abspath(__file__)
#project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file))) #Going 3 levels up to get to project root folder, 
#if project_root not in sys.path:
#    sys.path.insert(0, project_root)

from scripts.query_db.prompt_config_clv2 import query_clf_temp, fshot_temp, QUESTION_CATv2
from scripts.query_db.prompt_config_clv3 import query_clf_tempv3, fshot_temp, QUESTION_CAT
from scripts.query_db.config import DATA_DIR, clf_example_file, MODEL_CONF
from scripts.utils import load_data, extract_data
from scripts.run_llm_inferencev2 import BedrockTextGenerator

base_dir = os.path.dirname(__file__)

print('cwd_clf',os.getcwd())

'''This class contains the functions to generate fewshot prompt and to classify a question into categories by using an LLM'''
    
class FewShotClfBedrock():

    _allowed_model_ids = MODEL_CONF.keys()
    
    def __init__(self, modelid: str, model_region: str = None):
        if modelid not in self._allowed_model_ids:
            raise ValueError(f'Error: model_id should be chosen from {self._allowed_model_ids}')
        self.modelid = modelid
        self.model_region = model_region
        self.model_params = MODEL_CONF[modelid]

    def create_fshot_prompt(self, question: str, schema_str: str) -> str:
        """This function is to be used to generate fewshot prompt to help LLM classify question as 
        different categories

        Args:
            question (str): text query
            schema_str (str): database schema
        """
        examples = ''
        if 'claude-3' in self.modelid or 'nova' in self.modelid or 'llama' in self.modelid:
            # fshot_prompt = QUESTION_CAT.format(schema_str=schema_str,user_query = question)
            fshot_prompt = QUESTION_CAT.format(user_query = question)
        elif 'claude-v2' in self.modelid:
            # fshot_prompt = query_clf_temp.format(ex=examples, question=question) # Modify query_clf_temp
            fshot_prompt = QUESTION_CATv2.format(user_query=question)
        # print('Zshot_prompt',fshot_prompt)
        return fshot_prompt

    def generate_categories(self, question: str, schema_str: str) -> str:
        """This function is to be used to classify the question into different categories

        Args:
            question (str): text query
        """
        qtype_gen = ''
        prompt = self.create_fshot_prompt(question, schema_str)
        messages = [{"role": "user", "content":[{"text": question}]}]
        qtype_generator = BedrockTextGenerator(self.modelid, self.model_params, region=self.model_region)
        text_resp, error_msg = qtype_generator.generate(input_text=messages, prompt=prompt)
        if error_msg == '':
            qtype_gen = extract_data(text_resp)
        return qtype_gen
