import os
import sys
import re
import datetime
from scripts.query_db.prompt_config_clv2 import query_reasoning_temp
from scripts.query_db.prompt_config_clv3 import query_reasoning_tempv3
from scripts.query_db.config import DATA_DIR, MODEL_CONF, token_interpretation, reasoning_style, domain_vars_map, arith_ops
from scripts.utils import load_data, extract_data, log_error
from scripts.run_llm_inferencev2 import BedrockTextGenerator

base_dir = os.path.dirname(__file__)

reason_ans_prompt = '''You are an expert business analyst. 
Your task is to generate an explanation for a question based on numerical analysis on the data given in the 
<data></data> tag. Given some data in a tabular form with columns being the factors and rows referring to individual 
records or observations, provide a quantitatively supported explanation for a given question using the following thinking process:

1. From the question find the objective or variable that is being reasoned about.
2. From the data table within the <data></data> tag find the column that is similar or matches that variable.
3. Next, look for the factors which are the other columns in the data table and how they influence the objective variable
4. If the question is about explaining the relationships between the factor variables then do that with specific examples from the data
5. In the output explanation provide the steps by step thinking process
6. Percentage increase or decrease between before and after scenarios is calculated by finding the ratio of their difference (after minus before) and the 
before data point. If the result is negative there is a percentage decrease and vice versa.
7. For identifying trends, find the chronological first order differences between values of a variable. If the difference is decreasing the trend is downwards and vice versa.
8. Finding the correlation between variables gives the relationship between them. Two variables can be positively correlated, negatively correlated or independent of each other.
9. You cannot explain anything if the data is just a single value. In that case just report the value for the objective.
10. If there is a no data returned withn the <data></data> tag, politely express your inability to explain the observation.

Given the following data

<data>
{data}
</data>

explain the following question with proper quantitatively supported reasoning and return your answer inside the <answer></answer> tag. 

{question}

'''



"""This class contains the functions to generate fewshot prompt and pass the prompt to an LLM to generate deductive reasoning
"""
    
class FewShotReasonerBedrock():

    _allowed_model_ids = MODEL_CONF.keys()
    
    def __init__(self, modelid: str, model_region: str = None):
        if modelid not in self._allowed_model_ids:
            raise ValueError(f'Error: model_id should be chosen from {self._allowed_model_ids}')
        self.modelid = modelid
        self.model_region = model_region
        self.model_params = MODEL_CONF[modelid]

    def create_fshot_prompt(self, question: str, data: dict[list]) -> str:
        """This function is to be used to generate fewshot prompt

        Args:
            question (str): text query
            data (list): list containing the dataframe records retrieved from database to be used 
            for analysis
        Returns: Prompt
       
        """
        if 'claude-3' in self.modelid or 'nova' in self.modelid or 'llama' in self.modelid:
            fshot_prompt = reason_ans_prompt.format(question=question,\
                                                   data=data)
        #elif 'claude-v2' in self.modelid:
        #   fshot_prompt = query_reasoning_temp.format(token_intp=token_interpretation,\
        #                                            metric_vars=domain_vars_map,\
        #                                           style=reasoning_style,ex=None, \
        #                                           arith_ops=arith_ops,\
        #                                           data=data, question=question)
        print('fshot_prompt',fshot_prompt)
        return fshot_prompt

    def generate_reasoning(self, messages: list, question: str, data: dict[list]) -> str:
        """This function is to be used to pass the prompt to an LLM to generate deductive reasoning

        Args:
            messages(list): the list of content passed by user and responses from bot
            question (str): text query
            data (list): list containing the dataframe records retrieved from database to be used 
            for analysis
        Returns: response from LLM, error message
        """
        #reason_gen = ''
        response = ''
        error_msg = ''
        try:
            prompt = self.create_fshot_prompt(question, data)
            reason_generator = BedrockTextGenerator(self.modelid, self.model_params, region=self.model_region)
            text_resp, error_msg = reason_generator.generate(input_text=messages, prompt=prompt)
            if error_msg == '':
                print('text_resp',text_resp)
                response = extract_data(text_resp)
                #reason_gen = extract_data(text_resp, tag1='<factor_contribution>', 
                #                          tag2='</factor_contribution>')
                #calc_gen = extract_data(text_resp, tag1='<calculations>', tag2='</calculations>')
        except Exception as e:
            error_msg = str(e)
            log_error('FewShotReasonerBedrock', error_msg)
        #return reason_gen, error_msg
        return response, error_msg
