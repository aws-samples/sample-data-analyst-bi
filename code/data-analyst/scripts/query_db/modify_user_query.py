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

from scripts.query_db.prompt_config_clv2 import query_clf_temp, fshot_temp
from scripts.query_db.prompt_config_clv3 import query_clf_tempv3, fshot_temp, qpart_temp, question_mod_prompt
from scripts.query_db.config import DATA_DIR, clf_example_file, MODEL_CONF
from scripts.utils import load_data, extract_data
from scripts.run_llm_inferencev2 import BedrockTextGenerator

base_dir = os.path.dirname(__file__)

print('cwd_clf',os.getcwd())

"""This class contains the functions to generate fewshot prompt and pass the prompt to an LLM to  generate subqueries for a question. This is only required for deductive reasoning pertaining to why type questions"""
    
class FewShotModifierBedrock():
    _allowed_model_ids = MODEL_CONF.keys()
    
    def __init__(self, modelid, model_region: str = None):
        if modelid not in self._allowed_model_ids:
            raise ValueError(f'Error: model_id should be chosen from {self._allowed_model_ids}')
        self.modelid = modelid
        self.model_region = model_region
        self.model_params = MODEL_CONF[modelid]

    def create_fshot_prompt(self, question: str, query_type: str, schema_str: str, q_mod_prompt: str) -> str:
        """This function is to be used to generate fewshot prompt 

        Args:
            question (str): file path
            query_type (str): the different categories a question can be classified
        Returns: prompt
        """
        
        #df_prompt_ex = load_data(DATA_DIR, split_example_file)
        #nlq_list = df_prompt_ex['nlq'].values.tolist()
        #expl_list = df_prompt_ex['explanation'].values.tolist()
        #subq_list = df_prompt_ex['answer'].values.tolist()
        #rel_vars = domain_vars_map['relevant_metric_vars']
        #examples = ''''''
        #for i, nlq in enumerate(nlq_list):
        #    subqueries = ''''''
        #    explanation = expl_list[i]
        #    subq = subq_list[i]
        #    fshot_data = split_fshot_temp.format(idx=i, question=nlq, expl=explanation, 
        #                                         qparts=subq)
        #    examples += fshot_data
        #print('examples', examples)
        if query_type == '':
            query_type = 'reasoning'

        if query_type == 'reasoning':
            if 'claude-3' in self.modelid or 'nova' in self.modelid or 'llama' in self.modelid:
                #fshot_prompt = question_mod_prompt.format(schema_str=schema_str, 
                #                                  user_query=question)
                fshot_prompt = q_mod_prompt.format(schema_str=schema_str, 
                                                   user_query=question)                                   
            #elif 'claude-v2' in self.modelid:
            #    fshot_prompt = query_split_temp.format(qtype=query_type, metric_vars=domain_vars_map, 
            #                                       criteria=criteria,ex=examples, question=question)
        # print('fshot_prompt', fshot_prompt)
        return fshot_prompt

    def generate_subquery(self, messages: list, question: str, query_type: str, schema_str: str, q_mod_prompt: str) -> list[str]:
        """This function is to be used to invoke an LLM with a prompt to generate subqueries for a 
        question

        Args:
            messages(list): the list of content passed by user and responses from bot
            question (str): file path
            query_type (str): the different categories a question can be classified
        Returns: response from LLM
        """
        # print("qmod_prompt in generate subquery: \n", q_mod_prompt  )
        error_msg = ''
        response = ''
        prompt = self.create_fshot_prompt(question, query_type,schema_str, q_mod_prompt)
        messages = [{"role": "user", "content":[{"text": question}]}]
        qtype_generator = BedrockTextGenerator(self.modelid, self.model_params, region=self.model_region)
        text_resp, error_msg = qtype_generator.generate(input_text=messages, prompt=prompt)
        if error_msg == '':
            print('text_resp',text_resp)
            response = extract_data(text_resp)
        return response, error_msg, prompt
