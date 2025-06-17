import sys
sys.path.insert(0, '../')

import json
import boto3
import re
from botocore.config import Config
from scripts.config import LLM_CONF

config = Config(
    retries = {
        'max_attempts': 10,
        'mode': 'adaptive'
    }
)


class BedrockLLM:

    def __init__(self, model_id: str, region_name: str = "us-east-1", **kwargs):
        """_summary_

        Args:
            model_id (str): model id in bedrock
            kwargs: other sampling parameters
        """
        self._model_id = model_id
        self._region_name = region_name
        self._model_params = LLM_CONF[model_id]
        

        self._bedrock_runtime = boto3.client(service_name='bedrock-runtime', region_name=self._region_name, config=config)

    
    def __call__(self, prompt: str | list[dict[str, str]], system_prompt: str|None = None) -> str:
        if "claude-3" in self._model_id or "nova" in self._model_id:
            if isinstance(prompt, str):
                print('convert_completion_prompt_to_messages:', prompt.replace("\n", ""))
                prompt, system_prompt = self.convert_completion_prompt_to_messages(prompt)
            print('messages:', prompt)
            return self.invoke_message_api(messages=prompt, system_prompt=system_prompt)
        else:
            return self.invoke_completion_api(prompt=prompt)

    def invoke(self, *args, **kwargs) -> str:
        return self(*args, **kwargs)

    def invoke_message_api(self, messages: list[dict[str, str]], system_prompt: str|None = None) -> str:
        payload = {"messages": messages}
        if system_prompt is not None:
            payload["system"] = system_prompt
        if 'nova' in self._model_id:
            payload['inferenceConfig'] = self._model_params
            payload['inferenceConfig'].pop('performanceConfig', None)
        else:
            payload.update(self._model_params)
            payload.pop('performanceConfig', None)
        print('invoking with payload:', self._model_id, payload)
        body = json.dumps(payload)

        response = self._bedrock_runtime.invoke_model(modelId=self._model_id, body=body, performanceConfigLatency=LLM_CONF[self._model_id]['performanceConfig'])
        response_body = json.loads(response['body'].read().decode('utf-8'))

        try:
            if 'nova' in self._model_id:
                return response_body["output"]["message"]["content"][0]["text"]
            else:
                return response_body["content"][0]["text"]
        except Exception as e:
            print('Error in invoke_message_api:', e)
            return ""


    def invoke_completion_api(self, prompt: str) -> str:
        payload = {"prompt": prompt}
        payload.update(self._model_params)
        payload.pop('performanceConfig', None)
        print('invoking with payload:', self._model_id, payload)
        body = json.dumps(payload)
        response = self._bedrock_runtime.invoke_model(modelId=self._model_id, body=body, performanceConfigLatency=LLM_CONF[self._model_id]['performanceConfig'])
        response_body = json.loads(response['body'].read().decode('utf-8'))
        
        if 'llama' in self._model_id:
            return response_body["generation"]

        return response_body["completion"]


    def convert_completion_prompt_to_messages(self, prompt: str) -> tuple[list[dict[str, str]], str]:
        contents = [x.strip() for x in re.split(r"(\n\nHuman:|\n\nAssistant:)", prompt)]
        contents = [x for x in contents if x not in ("Human:", "Assistant:")]

        messages = []
        
        system_prompt = contents.pop(0)
        if len(system_prompt) == 0:
            system_prompt = None

        if len(contents) > 0 and len(contents[-1]) == 0:
            contents.pop()

        is_nova_model = "nova" in self._model_id.lower()

        for i, content in enumerate(contents):
            role = "user" if i % 2 == 0 else "assistant"

            if is_nova_model:
                message = {"role": role, "content": [{"text": content}]}
            else:
                message = {"role": role, "content": content}

            messages.append(message)

        return messages, system_prompt
