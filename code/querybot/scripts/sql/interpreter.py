import logging
import os
import pandas as pd
from scripts.utils import init_bedrock_llm
from scripts.config import AWS_REGION, LLM_CONF
from scripts.prompts import BR_IP_SYS_PROMPT, LLM_IP_PROMPTS, LLM_IP_PROMPTS_FINAL

logger = logging.getLogger(__name__)

os.environ['AWS_DEFAULT_REGION'] = AWS_REGION


class Interpreter:
    SUPPORTED_MODELS = LLM_CONF.keys()

    def __new__(cls, model_id: str, model_params: dict = None):
        if model_id not in cls.SUPPORTED_MODELS:
            raise ValueError(f'Error: {model_id} not in supported model {cls.SUPPORTED_MODELS}')

        return super(Interpreter, cls).__new__(cls)

    def __init__(self, model_id: str, model_params: dict = None):
        self.model_id = model_id
        self.model_params = model_params
        self._llm = init_bedrock_llm(self.model_id)

    def explain(self, question: str, result: pd.DataFrame):
        result = result.to_string()
        sql_prompt = LLM_IP_PROMPTS[self.model_id].format(question=question, result=result)
        if '{sys_prompt}' in LLM_IP_PROMPTS_FINAL[self.model_id]:
            final_prompt = LLM_IP_PROMPTS_FINAL[self.model_id].format(sys_prompt = BR_IP_SYS_PROMPT,
                                                                   sql_prompt = sql_prompt)
        else:
            final_prompt = LLM_IP_PROMPTS_FINAL[self.model_id].format(sql_prompt = sql_prompt)
        print (final_prompt)

        summary = self._llm(final_prompt, system_prompt=BR_IP_SYS_PROMPT).split("</response>")[0].replace("<response>", "")
        return summary


if __name__ == "__main__":
    t = Interpreter("anthropic.claude-v2:1", {"test": 2.1})
    print(t.model_id, t.model_params)
