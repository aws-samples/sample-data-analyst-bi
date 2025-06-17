import logging
import os
import pandas as pd
from scripts.utils import init_bedrock_llm, init_sagemaker_llm
from scripts.config import AWS_REGION, LLM_CONF
from scripts.prompts import BEDROCK_SYS_PROMPT, LLM_RECTIFIER_PROMPTS, LLM_RECTIFIER_PROMPTS_FINAL

logger = logging.getLogger(__name__)

os.environ['AWS_DEFAULT_REGION'] = AWS_REGION


class Rectifier:

    SUPPORTED_MODELS = LLM_CONF.keys()

    def __new__(cls, model_id: str, model_params: dict = None):
        if model_id not in cls.SUPPORTED_MODELS:
            raise ValueError(f'Error: {model_id} not in supported model {cls.SUPPORTED_MODELS}')

        return super(Rectifier, cls).__new__(cls)

    def __init__(self, model_id: str, model_params: dict = None):
        self.model_id = model_id
        self.model_params = model_params
        if self.model_id.startswith('ic-'):
            self._llm = init_sagemaker_llm(self.model_id)
        else:
            self._llm = init_bedrock_llm(self.model_id)

    def correct(self, database: str, question: str, sql: str, error: str, schema_meta:str):
        sys_prompt = BEDROCK_SYS_PROMPT.format(sql_database=database)
        sql_prompt = LLM_RECTIFIER_PROMPTS[self.model_id].format(question=question, sql_cmd=sql, syntax_error=error,schema=schema_meta)
        if self.model_id.startswith('ic-'):
            sql = self._llm(sql_prompt, system_prompt=sys_prompt).split("</sql>")[0].split("<sql>")[1]
        else:
            if '{sys_prompt}' in LLM_RECTIFIER_PROMPTS_FINAL[self.model_id]:
                final_prompt = LLM_RECTIFIER_PROMPTS_FINAL[self.model_id].format(sys_prompt=sys_prompt,
                                                                                sql_prompt=sql_prompt)
            else:
                final_prompt = LLM_RECTIFIER_PROMPTS_FINAL[self.model_id].format(sql_prompt=sql_prompt)
            sql = self._llm(final_prompt, system_prompt=sys_prompt).split("</sql>")[0].split("<sql>")[1]
        return sql
