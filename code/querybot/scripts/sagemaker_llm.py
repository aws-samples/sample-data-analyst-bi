import sys
sys.path.insert(0, '../')

import json
import boto3
import time


class SageMakerLLM:
    def __init__(self, endpoint_name: str, inference_component_name: str, region_name: str = "us-east-1", **kwargs):
        """Initialize SageMaker LLM client

        Args:
            endpoint_name (str): Name of the SageMaker endpoint
            inference_component_name (str): Name of the inference component
            hf_tokenizer_id (str): Hugging Face tokenizer ID
            region_name (str, optional): AWS region name. Defaults to "us-east-1".
        """
        self._endpoint_name = endpoint_name
        self._inference_component_name = inference_component_name
        self._region_name = region_name

        print('Initializing SageMakerLLM client with endpoint_name:', endpoint_name, 'inference_component_name:', inference_component_name, 'region_name:', region_name)
        
        # Initialize SageMaker runtime client
        self._sagemaker_runtime = boto3.client(
            service_name='sagemaker-runtime',
            region_name=self._region_name
        )
    
    def __call__(self, prompt: str, system_prompt: str = '', max_retries: int = 10) -> str:
        """Main interface for generating responses

        Args:
            prompt (Union[str, List[Dict[str, str]]]): Either a string prompt or list of message dicts
            system_prompt (Optional[str]): System prompt to prepend. Defaults to None.
            max_retries (int): Maximum number of retry attempts. Defaults to 10.

        Returns:
            str: Generated response
        """
        assert isinstance(prompt, str), "Prompt must be a string"
        assert isinstance(system_prompt, str), "System prompt must be a string"

        tokenized_prompt = self.tokenize(prompt, system_prompt)
    
        return self.invoke_endpoint(tokenized_prompt, max_retries=max_retries)

    def invoke(self, *args, **kwargs) -> str:
        """Alias for __call__"""
        return self(*args, **kwargs)

    def invoke_endpoint(self, tokenized_prompt: str, max_retries: int = 10) -> str:
        """Invoke SageMaker endpoint with retry mechanism

        Args:
            tokenized_prompt (str): Tokenized prompt
            max_retries (int): Maximum number of retry attempts

        Returns:
            str: Generated response
        """
        attempt = 0
        while attempt < max_retries:
            try:
                print('Invoking sagemaker endpoint:', tokenized_prompt)
                response = self._sagemaker_runtime.invoke_endpoint(
                    EndpointName=self._endpoint_name,
                    InferenceComponentName=self._inference_component_name,
                    ContentType="application/json",
                    Accept="application/json",
                    Body=json.dumps({
                        "inputs": tokenized_prompt
                    })
                )
                
                response_body = json.loads(response["Body"].read().decode("utf-8"))[0]
                full_text = response_body.get("generated_text", "")
                result = full_text[len(tokenized_prompt):].lstrip() if full_text.startswith(tokenized_prompt) else full_text

                return result
                
            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {str(e)}")
                attempt += 1
                if attempt < max_retries:
                    time.sleep(30)  # Wait before retrying
                    
        raise Exception("Failed to get response after maximum retries")
    
    def tokenize(self, prompt: str, system_prompt: str) -> list[dict[str, str]]:
        """Tokenize prompt and optionally prepend system prompt

        Args:
            prompt (str): Prompt to tokenize
            system_prompt (Optional[str]): System prompt to prepend. Defaults to None.

        Returns:
            List[Dict[str, str]]: List of message dictionaries
        """
        if 'deepseek' in self._inference_component_name:
            tokenized_prompt = f'<｜begin▁of▁sentence｜><｜User｜>{system_prompt}\n\n{prompt}\n<｜Assistant｜><think>\n\n\n</think>\n\n'
        elif 'llama-3' in self._inference_component_name:
            tokenized_prompt = f'<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n{system_prompt}\n\n<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n{prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n'
        else:
            raise Exception('Unsupported model')

        return tokenized_prompt
    