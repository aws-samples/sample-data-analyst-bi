import os
import sys
project_root = '/home/sagemaker-user/data_analyst_bot/da_refactor'
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import boto3
from botocore.config import Config
import pandas as pd
#import os
# import torch -- used in SQL coder
#import pickle
import numpy as np
import time
import json
#import re -- used in SQL coder model
#import sqlparse -- -- used in SQL coder model
#import gc -- used in SQL coder model
#from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig -- used in SQL coder model
#from tqdm import tqdm
from scripts.query_db.config import AWS_REGION, MODEL_CONF
from scripts.utils import log_error


"""The class below contains the functions to invoke functions to augment the prompt with Bedrock LLM parameters  and invoke Claude and Titan embedding models to generate text"""
    
class BedrockTextGenerator():
    
    def __init__(self, modelid, params):
        self.modelid = modelid
        self.model_params = params
        self.config = Config(
            retries = {
                'max_attempts': 10,
                'mode': 'adaptive'
            }
        )
        self.bedrock_client = boto3.client("bedrock-runtime", region_name=AWS_REGION, config=self.config)

        try:
            self.guardrail_config = {
                "guardrailIdentifier": os.environ['GUARDRAIL_ID'],
                "guardrailVersion": os.environ['GUARDRAIL_VERSION'],
                "trace": "enabled"
            }
        except Exception as e:
            print('Guardrail setup failed:', e)
            self.guardrail_config = None

        ## this is for database source, for file based source, import from the right script -    scripts.query_file.config
        
    def __create_claude_body(self, input_text: str):
        """This function is to be used to augment prompt with claude parametes for text completion API for claude versions less than v3

        Args:
            input_text: the text query
        Returns: The payload to be sent to LLM
        """
        body = {
            "prompt": input_text,
            "max_tokens_to_sample": self.model_params['max_tokens_to_sample'],
            "temperature": self.model_params['temperature'],
            "top_k": self.model_params['top_k'],
            "top_p": self.model_params["top_p"],
            "stop_sequences": self.model_params["stop_sequences"]
        }
        return body
    
    def __create_claudev2_messages_body(self, messages: list, prompt: str):
        """This function is to be used to augment prompt with claude parametes for messages completion API for for claude versions less than v3

        Args:
            messages: the list of content from user and bot
            prompt: the actual prompt consisting of instructions, context etc excluding the text query
        Returns: The payload to be sent to LLM
        """
        system = prompt
        body = {
            "messages": messages,
            "system": system,
            "max_tokens": self.model_params['max_tokens_to_sample'],
            "temperature": self.model_params['temperature'],
            "anthropic_version": "",
            "top_k": self.model_params['top_k'],
            "top_p": self.model_params["top_p"],
            "stop_sequences": self.model_params["stop_sequences"]
        }
        return body
    
    def __create_claudev3_messages_body(self, input_text: list, prompt: str):
        """
        This function is for augmenting prompt for Anthropic Claude models for the Messages API for claude v3
        https://docs.anthropic.com/claude/reference/messages_post
        Args:
            input_text: the list of content from user and bot
            prompt: the actual prompt consisting of instructions, context etc excluding the text query
        Returns: The payload to be sent to LLM
        """
        system = prompt
        body = {
            "messages": input_text,
            "max_tokens": self.model_params['max_tokens'],
            "system": system,
            "temperature": self.model_params['temperature'],
            "anthropic_version": "",
            "top_k": self.model_params['top_k'],
            "top_p": self.model_params["top_p"],
            "stop_sequences": self.model_params["stop_sequences"]
        }
        return body
    
    def __create_claudev3_converse(self, input_text: list, prompt: str):
        """
        This function is for augmenting prompt for Anthropic Claude models for the Messages API.
        https://docs.anthropic.com/claude/reference/messages_post
        Args:
            input_text: the list of content from user and bot
            prompt: the actual prompt consisting of instructions, context etc excluding the text query
        Returns: The prompt, list of content of user and bot, inference parameters
        """
        system = [{"text": prompt}]
        # Message structure for Bedrock Claude-3
        messages = input_text
        inferenceConfig = {"maxTokens": self.model_params['maxTokens'],
            "temperature": self.model_params['temperature'],
            "topP": self.model_params["topP"]
        }
        return system, messages, inferenceConfig

    def __get_claude_response(self, input_text: str) :
        """
        This function is to be used to invoke claude models for text completion API for versions less than v3
        Args:
            input_text: the text query
        Returns: The text generated from LLM
        """
        body = self.__create_claude_body(input_text)
        text_resp = ''
        try:
            response = self.bedrock_client.invoke_model(modelId=self.modelid, body=json.dumps(body), performanceConfigLatency=MODEL_CONF[self.modelid]['performanceConfig'])
            response = json.loads(response['body'].read().decode('utf-8'))
            text_resp, stop_reason = response['completion'],response['stop_reason']
        except Exception as e:
            error_msg = str(e)
            log_error('BedrockTextGenerator', error_msg)

        return text_resp
    
    def __get_claude_messages_response(self, input_text, prompt):
        """
        This function is to be used to invoke claude models for messages API for V3 models
        Args:
            input_text: the text query
            prompt: the actual prompt consisting of instructions, context etc excluding the text query
        Returns: The text generated from LLM
        """
        response = ''
        error_msg = ''
        try:
            body = self.__create_claudev3_messages_body(input_text, prompt)
            print('body inference', body)
            response = self.bedrock_client.invoke_model(modelId=self.modelid, body=json.dumps(body), performanceConfigLatency=MODEL_CONF[self.modelid]['performanceConfig'])
            response = json.loads(response['body'].read().decode('utf-8'))
            response = response['content'][0]['text']
        except Exception as e:
            error_msg = str(e)
            print('error_msg', error_msg)
            log_error('BedrockTextGenerator', error_msg)
        return response, error_msg
    
    
    def __get_claude_messages_converse_response(self, input_text, prompt, apply_guardrail=False):
        """
        This function is to be used to invoke claude models for messages API
        Args:
            input_text: the text query
            prompt: the actual prompt consisting of instructions, context etc excluding the text query
        Returns: The text generated from LLM
        """
        response = ''
        error_msg = ''
        try:
            system, messages, inferenceConfig = self.__create_claudev3_converse(input_text, prompt)

            kwargs = {
                "modelId": self.modelid,
                "messages": messages,
                "system": system,
                "inferenceConfig": inferenceConfig,
                "performanceConfig": {
                    'latency': MODEL_CONF[self.modelid]['performanceConfig']
                }
            }

            if self.guardrail_config and apply_guardrail:
                kwargs["guardrailConfig"] = self.guardrail_config
            
            print('payload:', kwargs)

            response = self.bedrock_client.converse(**kwargs)
            
            print('response',response)
            response = response['output']['message']['content'][0]['text']
        except Exception as e:
            error_msg = str(e)
            print('error_msg', error_msg)
            log_error('BedrockTextGenerator', error_msg)
        return response, error_msg

    def get_titan_embeddings(self, data):
        """
        This function is to be used to invoke the Bedrock Titan embedding model
        Args:
            data: the text query from a user or list of text queries from training set to index
        Returns: The list of embeddings for the questions
            
        """

        embs_dict = {}
        modelId = self.modelid
        accept = self.model_params['accept']
        contentType = self.model_params['contentType']
        data = [data] if type(data) == str else data
        for i, sentence in enumerate(data):
            try:
                sentence = json.dumps({"inputText": sentence})
                response = self.bedrock_client.invoke_model(body=sentence, modelId=modelId, 
                                            accept=accept, contentType=contentType)
                response_body = json.loads(response.get('body').read())
                embedding = response_body.get('embedding')
                #embedding = np.array(embedding)
                embs_dict[i] = np.array(embedding)
            except Exception as e:
                print(e)
        embs_list = np.array([list(embs_dict[key]) for key in embs_dict],dtype="float32")
        return embs_list
    
    def get_cohere_embeddings(self, data):
        """
        This function is to be used to invoke the Bedrock Cohere embedding model
        Args:
            data: the text query from a user or list of text queries from training set to index
            
        Returns: The list of embeddings for the questions
        """
        embs_dict = {}
        modelId = "cohere.embed-english-v3"
        accept = "*/*"
        contentType = 'application/json'
        data = [data] if type(data) == str else data
        config = Config(
            retries = {
                'max_attempts': 10,
                'mode': 'adaptive'
            }
        )
        bedrock_client = boto3.client(service_name='bedrock-runtime', config=config)
        print(data)
        for i, sentence in enumerate(data):

            try:
                sentence = json.dumps({"texts": [sentence], "input_type": 'search_document'})
               # print(sentence)
                response = bedrock_client.invoke_model(body=sentence, modelId=modelId, 
                                            accept=accept, contentType=contentType)
                response_body = json.loads(response.get('body').read())
                embedding = response_body.get('embeddings')[0]
                embs_dict[i] = np.array(embedding)
            except Exception as e:
                print(e)
        embs_list = np.array([list(embs_dict[key]) for key in embs_dict],dtype="float32")
        return embs_list
    
    def generate(self, prompt, input_text=None, apply_guardrail=False):
        """
        This function is to be used to determine the appropriate LLM to invoke 
        Args:
            input_text: the text query from a user or list of content from user and bot
            prompt: the actual prompt consisting of instructions, context etc excluding the text query
        Returns: The text generated from LLM
        """
        if 'claude-3' in self.modelid or 'nova' in self.modelid or 'llama' in self.modelid:
            #text_resp, error_msg = self.__get_claude_messages_response(input_text, prompt)
            # print('messages', input_text)
            text_resp, error_msg = self.__get_claude_messages_converse_response(input_text, prompt, apply_guardrail)
        elif 'claude-v2' in self.modelid:
            text_resp = self.__get_claude_response(prompt)
        elif 'claude-instant' in self.modelid:
            text_resp = self.__get_claude_response(prompt)
        return text_resp, error_msg

"""The class below contains the functions to invoke functions to augment the prompt with SQL coder 7b LLM parameters and invoke SQLCoder 7b-2 to generate text
"""

''' 
Commenting out this section as we use only claude models       
class SQLCoderGenerator():
    
    def __init__(self, modelid, params):

        self.modelid = modelid
        self.model_params = params
        self.tokenizer = AutoTokenizer.from_pretrained(modelid)
        self.model = AutoModelForCausalLM.from_pretrained(
        modelid,
        trust_remote_code=True,
        torch_dtype=torch.float16,
        device_map="auto",
        use_cache=True)
       
    def generate(self, prompt: str):
        """
        This function is to be used to generate text from SQLCoder 7b-2 and extract SQL from the generated 
        text
        Args:
            prompt: the actual prompt consisting of instructions, context etc excluding the text query
        Returns: The SQL generated from LLM
        """
        sql = ''
        try:
            print('prompt', prompt)
            inputs = self.tokenizer(prompt, return_tensors="pt").to("cuda")
            max_new_tokens = self.model_params['max_new_tokens']
            num_return_sequences = self.model_params['num_return_sequences']
            do_sample = self.model_params['do_sample']
            num_beams = self.model_params['num_beams']
            with torch.no_grad():
                generated_ids = self.model.generate(
                    **inputs,
                    num_return_sequences = num_return_sequences,
                    eos_token_id = self.tokenizer.eos_token_id,
                    pad_token_id = self.tokenizer.eos_token_id,
                    max_new_tokens=max_new_tokens,
                    do_sample=do_sample,
                    num_beams=num_beams,
                )
                outputs = self.tokenizer.batch_decode(generated_ids, skip_special_tokens=True)

                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            generated_sql = sqlparse.format(outputs[0].split("[SQL]")[-1], reindent=True)
            print('generated_sql', generated_sql)
            sql = re.sub('\n', ' ', generated_sql).strip()
            del inputs
            del generated_ids
            del outputs
            del self.modelid
            gc.collect()
        except Exception as e:
            error_msg = str(e)
            print('error_msg', error_msg)
            log_error('SQLCoderGenerator', error_msg)
        return sql

'''