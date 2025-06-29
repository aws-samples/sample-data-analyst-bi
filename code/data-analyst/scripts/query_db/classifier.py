import os
import sys
project_root = '/home/sagemaker-user/data_analyst_bot/da_refactor'
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from scripts.query_db.prompt_config_clv2 import query_clf_temp, fshot_temp
from scripts.query_db.prompt_config_clv3 import query_clf_tempv3, fshot_temp
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

    def create_fshot_prompt(self, question: str) -> str:
        """This function is to be used to generate fewshot prompt to help LLM classify question as 
        different categories

        Args:
            question (str): text query
        """
        df_prompt_ex = load_data(DATA_DIR, clf_example_file)
        nlq_list = df_prompt_ex['nlq'].values.tolist()
        category_list = df_prompt_ex['category'].values.tolist()
        examples = ''''''
        for i, nlq in enumerate(nlq_list):
            category = category_list[i]
            fshot_data = fshot_temp.format(idx=i, question=nlq, answer=category)
            examples += fshot_data
        print('examples',examples)
        if 'claude-3' in self.modelid or 'nova' in self.modelid or 'llama' in self.modelid:
            fshot_prompt = query_clf_tempv3.format(ex=examples)
        elif 'claude-v2' in self.modelid:
            fshot_prompt = query_clf_temp.format(ex=examples, question=question)
        # print('fshot_prompt',fshot_prompt)
        return fshot_prompt

    def generate_categories(self, question: str) -> str:
        """This function is to be used to classify the question into different categories

        Args:
            question (str): text query
        """
        qtype_gen = ''
        prompt = self.create_fshot_prompt(question)
        qtype_generator = BedrockTextGenerator(self.modelid, self.model_params, region=self.model_region)
        text_resp, error_msg = qtype_generator.generate(input_text=question, prompt=prompt)
        if error_msg == '':
            qtype_gen = extract_data(text_resp)
        return qtype_gen
