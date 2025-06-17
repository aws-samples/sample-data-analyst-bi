# bedrock configs
AWS_REGION = 'us-east-1'
S3_BUCKET = 'td-gai-2023'
VPCE_ID = "vpce-0bf530fcbf9a8d324" #ID of the VPC Endpoint (VPCE) covering the VPC, Subnet and Security Group associated with the EC2 / SM instance running the app - this will be used to access OpenSearch (for ICL)
DB_CONF_PATH = '../conf/db_config.yaml'
DATA_DIR = '../data'
MODELS_DIR = "../models"
LLM_CONF = {
    "anthropic.claude-v2:1": {
        "temperature": 0,
        "top_p": 1,
        "top_k": 250,
        "max_tokens_to_sample": 2000,
        "stop_sequences": ["Human:"],
        "performanceConfig": "standard"
    },
    "anthropic.claude-instant-v1": {
        "temperature": 0,
        "top_p": 1,
        "top_k": 250,
        "max_tokens_to_sample": 2000,
        "stop_sequences": ["Human:"],
        "performanceConfig": "standard"
    },
    "anthropic.claude-3-sonnet-20240229-v1:0": {
        "temperature": 0,
        "top_p": 1,
        "top_k": 250,
        "max_tokens": 200,
        "anthropic_version": "bedrock-2023-05-31",
        "stop_sequences": ["</sql>"],
        "performanceConfig": "standard"
    },
    "anthropic.claude-3-haiku-20240307-v1:0": {
        "temperature": 0,
        "top_p": 1,
        "top_k": 250,
        "max_tokens": 200,
        "anthropic_version": "bedrock-2023-05-31",
        "stop_sequences": ["</sql>"],
        "performanceConfig": "standard"
    },
    "anthropic.claude-3-5-sonnet-20240620-v1:0": {
        "temperature": 0,
        "top_p": 1,
        "top_k": 250,
        "max_tokens": 200,
        "anthropic_version": "bedrock-2023-05-31",
        "stop_sequences": ["</sql>"],
        "performanceConfig": "standard"
    },
    "anthropic.claude-3-5-sonnet-20241022-v2:0": {
        "temperature": 0,
        "top_p": 1,
        "top_k": 250,
        "max_tokens": 200,
        "anthropic_version": "bedrock-2023-05-31",
        "stop_sequences": ["</sql>"],
        "performanceConfig": "standard"
    },
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0": {
        "temperature": 0,
        "top_p": 1,
        "top_k": 250,
        "max_tokens": 200,
        "anthropic_version": "bedrock-2023-05-31",
        "stop_sequences": ["</sql>"],
        "performanceConfig": "standard"
    },
    "us.anthropic.claude-3-7-sonnet-20250219-v1:0": {
        "temperature": 0,
        "top_p": 1,
        "top_k": 250,
        "max_tokens": 200,
        "anthropic_version": "bedrock-2023-05-31",
        "stop_sequences": ["</sql>"],
        "performanceConfig": "standard"
    },
    "us.anthropic.claude-3-5-haiku-20241022-v1:0": {
        "temperature": 0,
        "top_p": 1,
        "top_k": 250,
        "max_tokens": 200,
        "anthropic_version": "bedrock-2023-05-31",
        "stop_sequences": ["</sql>"],
        "performanceConfig": "optimized"
    },
    "ic-deepseek-r1-distill-llama-70b": {
       "temperature": 0,
       "maxTokens": 4096,
       "performanceConfig": "standard"
   },
   "ic-llama-3-3-70b-instruct": {
       "temperature": 0,
       "maxTokens": 4096,
       "performanceConfig": "standard"
   },
    "amazon.nova-micro-v1:0": {
       "temperature": 0,
       "topP": 1.0,
       "topK": 100,
       "maxTokens": 200,
        "performanceConfig": "standard"
   },
   "amazon.nova-lite-v1:0": {
       "temperature": 0,
       "topP": 1.0,
       "topK": 100,
       "maxTokens": 200,
        "performanceConfig": "standard"
   },
   "amazon.nova-pro-v1:0": {
       "temperature": 0,
       "topP": 1.0,
       "topK": 100,
       "maxTokens": 200,
        "performanceConfig": "standard"
   },
   "amazon.nova-pro-v1:0": {
       "temperature": 0,
       "maxTokens": 200,
        "performanceConfig": "standard"
   },
    "us.meta.llama3-3-70b-instruct-v1:0": {
        "temperature": 0,
        "top_p": 1,
        "max_gen_len": 2000,
        "performanceConfig": "standard"
    },
    "amazon.titan-embed-text-v2:0": {
        "temperature": 0,
        "top_p": 1,
        "max_tokens_to_sample": 2000,
        "performanceConfig": "standard"
    },
    "hf_codellama": {
        "top_p": 0.9, 
        "temperature": 0.1, 
        "top_k": 40, 
        "max_new_tokens": 300,
        "performanceConfig": "standard"
    }
}

SUPPORTED_HF_LLMS = ["codellama/CodeLlama-7b-Instruct-hf", "defog/sqlcoder-7b-2"]
HF_LLM_PROMPT_KEYS = {"codellama/CodeLlama-7b-Instruct-hf":"hf_codellama", "defog/sqlcoder-7b-2":"hf_sqlcoder2"}

#CODELLAMA_INF_PARAMS = {"top_p": 0.9, "temperature": 0.1, "top_k": 40, "max_new_tokens": 300}

# AOSS_RELEVANCE_THRESHOLD = 0.001
# CACHE_THRESHOLD = 0.001

AOSS_RELEVANCE_THRESHOLD = 0.92
CACHE_THRESHOLD = 0.90

