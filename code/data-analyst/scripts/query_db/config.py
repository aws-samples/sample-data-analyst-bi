"""The file contains various parameters required in the end to end workflow for usecases where data from databases are required for analysis
"""
import os

# SQL Generator Lambda function
SQL_Gen_Lambda = 'lambda-func'

## To be used for OpensearchServerless(OSS) vector database & Bedrock invocation
# Read from environment variable, fallback to us-east-1 for backward compatibility
AWS_REGION = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
## The base dir containing the folders
#HOME_DIR = '/home/sagemaker-user/data_analyst_bot/da_refactor/' ## the home dir path

# Base directory configuration
## The base dir containing the folders

def is_lambda_environment():
    """Check if code is running in AWS Lambda environment"""
    return bool(os.getenv('AWS_LAMBDA_FUNCTION_NAME'))

if is_lambda_environment():
    HOME_DIR = '/tmp'
else:
    HOME_DIR = '/home/sagemaker-user/data_analyst_bot/da_refactor'

## the directory where the fewshot training files(text,sql), aoss_config, schema files  are stored
DATA_DIR = os.path.join(HOME_DIR, 'db_data')

META_DIR = os.path.join(DATA_DIR, 'input_data')

## path to store the chat history in local
CHAT_DIR_LOCAL = os.path.join(DATA_DIR, 'chat_out') #

## path to store the chat history in S3. This should be created
CHAT_S3 = 'data-analysts-deploy-memory-bucket' 

## The vector index path for faiss local storage
INDEX_DIR = os.path.join(DATA_DIR, 'vector_index')

## the path  to the local database
DB_PATH = os.path.join(DATA_DIR, 'database/data/sql_reasoningv2.db')

## The vector index name for faiss local storage
INDEX_NAME = 'train_emb_index'

## Open search host name
AOSS_HOST_FILE =   os.path.join(DATA_DIR, "aoss_host.txt")

## Open search parameters file
AOSS_PARAMS_FILE = os.path.join(DATA_DIR, 'aoss_config.yaml')

##The data retrieved from SQL is saved to this filename which is used for generating plots
PLOT_FILE = 'sql_db_out.csv' 

chat_save = 'S3' ## values: 'local' for storing locally, 'S3' for storing in S3 bucket

## Number of interactions to keep in the chat history for answer generation
context_hist_size = 5

## Number of interactions to keep in the chat history for plot generation
context_plot_hist_size = 3

## Bedrock & HF LLM parameters
MODEL_CONF = {
   "anthropic.claude-v2:1": {
        "temperature": 0,
        "top_p": 1.0,  # 1
        "top_k": 280,  # 250
        "max_tokens_to_sample": 1000,
        "stop_sequences": ["Human:"],
        "performanceConfig": "standard"
   },
   "anthropic.claude-instant-v1": {
        "temperature": 0,
        "top_p": 1.0,  # 1
        "top_k": 280,  # 250
        "max_tokens_to_sample": 1000,
        "stop_sequences": ["Human:"],
        "performanceConfig": "standard"
   },
   "anthropic.claude-3-sonnet-20240229-v1:0": {
        "temperature": 0,
        "topP": 1.0,  # 1
        "top_k": 280,  # 250
        "maxTokens": 2000,
        "stop_sequences": ["Human:"],
        "performanceConfig": "standard"
   },
   "anthropic.claude-3-5-sonnet-20240620-v1:0": {
        "temperature": 0,
        "topP": 1.0,  # 1
        "top_k": 280,  # 250
        "maxTokens": 2000,
        "stop_sequences": ["Human:"],
        "performanceConfig": "standard"
   },
   "us.anthropic.claude-3-5-sonnet-20241022-v2:0": {
        "temperature": 0,
        "topP": 1.0,  # 1
        "top_k": 280,  # 250
        "maxTokens": 2000,
        "stop_sequences": ["Human:"],
        "performanceConfig": "standard"
   },
   "us.anthropic.claude-3-7-sonnet-20250219-v1:0": {
        "temperature": 0,
        "topP": 1.0,  # 1
        "top_k": 280,  # 250
        "maxTokens": 2000,
        "stop_sequences": ["Human:"],
        "performanceConfig": "standard"
   },
   "anthropic.claude-3-haiku-20240307-v1:0": {
        "temperature": 0,
        "topP": 1.0,  # 1
        "top_k": 280,  # 250
        "maxTokens": 2000,
        "stop_sequences": ["Human:"],
        "performanceConfig": "standard"
   },
   "us.anthropic.claude-3-5-haiku-20241022-v1:0": {
        "temperature": 0,
        "topP": 1.0,  # 1
        "top_k": 280,  # 250
        "maxTokens": 2000,
        "stop_sequences": ["Human:"],
        "performanceConfig": "optimized"
   },
   "amazon.nova-micro-v1:0": {
        "temperature": 0,
        "topP": 1.0,
        "topK": 100,
        "maxTokens": 2000,
        "performanceConfig": "standard"
   },
   "amazon.nova-lite-v1:0": {
        "temperature": 0,
        "topP": 1.0,
        "topK": 100,
        "maxTokens": 2000,
        "performanceConfig": "standard"
   },
   "amazon.nova-pro-v1:0": {
        "temperature": 0,
        "topP": 1.0,
        "topK": 100,
        "maxTokens": 2000,
        "performanceConfig": "standard"
   },
   "us.meta.llama3-3-70b-instruct-v1:0": {
        "temperature": 0,
        "topP": 1.0,
        "topK": 100,
        "maxTokens": 2000,
        "performanceConfig": "standard"
   },
   "amazon.titan-embed-text-v1": {
        "contentType": "application/json",
        "accept": "*/*",
        "performanceConfig": "standard"
   },
   "amazon.titan-embed-text-v2:0": {
        "contentType": "application/json",
        "accept": "*/*",
        "performanceConfig": "standard"
   },
   "cohere.embed-english-v3": {
       "contentType": "application/json",
       "accept": "*/*",
        "performanceConfig": "standard"
   },
   "cohere.embed-multilingual-v3": {
        "contentType": "application/json",
        "accept": "*/*",
        "performanceConfig": "standard"
   },
   "defog/sqlcoder-7b-2": {
        "max_new_tokens": 400,
        "num_return_sequences": 1,
        "do_sample": False,
        "num_beams": 1,
        "performanceConfig": "standard"
   }
}

## Mapping between embedding model and embedding dimensions
emb_model_dim = {
    'cohere.embed-english-v3': 1024, 
    'cohere.embed-multilingual-v3': 1024,
    'amazon.titan-embed-text-v1' : 1536,
    'amazon.titan-embed-text-v2:0' : 1024
    }
  

## Tables which are not viewable by Perosnas; Here persona 1 can view all tables and persona2 cannot view sales table

persona_tabs_excl_map = {'persona1':[None],\
                   'persona2':['sales']}

## The prompt type to be used for SQL generation
prompt_type = 'zeroshot' ## values: 'fewshot', 'zeroshot', 'fewshot_cot'

## number of fewshot examples required for subqueries involving generating SQL for retrieving data 
n_SHOTS=3 ## this is only configurable when prompt_type is not zero_shot. Should be a number greater than 0

## Use all tables or only relevant tables in the prompt for a particular question
all_tables = False ## Set to True if all table names are to be used in the prompt, else False

## whether local indexing or api based indexing to be used, possible values: 'aoss' for opensearchserverless and 'local' for storing faiss index locally
index_type = 'local'

## If local vector database is used, select faiss
index_model = 'faiss'

## LLM used to generate embeddings
emb_model = "cohere.embed-multilingual-v3" # values - "amazon.titan-embed-text-v2:0", "amazon.titan-embed-text-v1", "cohere.embed-english-v3", "cohere.embed-multilingual-v3"

## Whehter To decompose a question into sub queries using rule based or LLM
question_classif = 'model' ## possible values - 'rule','model' 

## To classify a question into one of the categories using rule based logic
words_cat_reason = ['why'] ## reasoning type question
#words_cat_data_ret_plot = ['plot', 'chart','charts'] ## plot type question
words_cat_data_ret_simple = ['what','how'] ## simple retrieval type question

# LLMs used in the workflow
# anthropic.claude-3-5-sonnet-20240620-v1:0
# us.anthropic.claude-3-5-sonnet-20241022-v2:0
# anthropic.claude-3-sonnet-20240229-v1:0

MODEL_IDS = {
    'CLAUDE_3_HAIKU': 'anthropic.claude-3-haiku-20240307-v1:0',
    'CLAUDE_3_SONNET': 'anthropic.claude-3-sonnet-20240229-v1:0',
    'CLAUDE_3_5_SONNET_V1': 'anthropic.claude-3-5-sonnet-20240620-v1:0',
    'CLAUDE_3_5_SONNET_V2': 'us.anthropic.claude-3-5-sonnet-20241022-v2:0',
    'CLAUDE_3_7_SONNET_V1': "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    'CLAUDE_3_5_HAIKU': 'us.anthropic.claude-3-5-haiku-20241022-v1:0',
    'LLAMA_3_2_11B': 'meta.llama3-2-11b-instruct-v1:0',
    'LLAMA_3_2_90B': 'meta.llama3-2-90b-instruct-v1:0',
}

classifier_llm =  MODEL_IDS['CLAUDE_3_5_HAIKU']  ## to classify a question as reasoning/retrieval/retrieval & computation
splitter_llm =  MODEL_IDS['CLAUDE_3_5_HAIKU']  ## to decompose a question into subqueries
sql_llm  = MODEL_IDS['CLAUDE_3_5_SONNET_V2'] ## availabe models:"defog/sqlcoder-7b-2" , "anthropic.claude-v2:1" to generate SQL for a question/sub queries
reasoner_llm =  MODEL_IDS['CLAUDE_3_5_HAIKU'] ## to generate answers for abductive reasoning type question
table_en_llm = MODEL_IDS['CLAUDE_3_5_HAIKU'] ## to convert structured data to natural language
plot_llm = MODEL_IDS['CLAUDE_3_5_HAIKU'] ## to generate python code to generate plots
text_tabs_llm = MODEL_IDS['CLAUDE_3_5_HAIKU'] ## to identify tables related to a text query . This is to be used to determine whether a persona is elgible for viewing tables and also filtering relevant tables required to generate sql

intent_llm = MODEL_IDS['CLAUDE_3_5_HAIKU']
rectifier_llm = MODEL_IDS['CLAUDE_3_5_SONNET_V2'] ## rectifying  a wrong SQL

## The filenames  having the fewshot examples which are required to augment the prompt

## fewshot example file if using processed file
clf_example_file = 'query_clf_ex.csv'
## fewshot example file for splitting question into subqueries
split_example_file = 'query_splitter_ex.csv'
## fewshot example file for generating SQL
text_sql_example_file = 'query_sql_ex.csv'
## fewshot example file for plotting
plot_ex_file = 'plot_ex_v0.csv'

## The files containing the description of the tables and columns
table_meta_file = 'table_meta.csv'
col_meta_file = 'col_meta.csv'
metric_meta_file = 'metric_meta.csv'

## the metric and the corresponding dependent factors for business context

##Sample
domain_vars_map = """1.sales depends on 'TotalMarkdown', 'Temperature', 'Fuel_Price', 'CPI', 'Holiday' """

## the schema file name which has the tables and column names
schema_file = 'schema.csv'

## the threshold of number of records which can be retrieved above which the system will raise error
num_record_thresh = 1000

## the threshold of the time of execution(secs) of SQL above which the system will raise error
exec_time_thresh = 20

## the file storing the errors arising out of the application
error_log_file = 'error_log.txt'

## the rules required to split a main question into subquery. This is to be added to the prompt
criteria = """1.if the main question is a "reasoning" based question, one of the subquestions you create should ask for retrieving the data for factors and the data for the metric. The last subquestion should be the main question\n2.Assign the subquestions with one of the categories: retrieval or reasoning. The "retrieval" type subquestions ask for getting the data, "reasoning" based subquestions ask why something happen or doing the causal analysis"""

## the meaning of business specific words 
glossary = None
filter_rules = None

## the meaning of business specific words 
token_interpretation = """1. "Markdowns" --> The discounts given on a product. Higher the discounts, higher the sales of a product """

##sample
table_joins = '''-- sales.Store can be joined with markdown.Store\n-- sales.Store can be joined with holiday.Store\n-- sales.Store can be joined with inflation.Store\n-- sales.Store can be joined with fuelprice.Store\n-- sales.Store can be joined with temperature.Store\n-- sales.Week can be joined with markdown.Week\n-- sales.Week can be joined with inflation.Week\n-- sales.Week can be joined with holiday.Week\n-- sales.Week can be joined with fuelprice.Week\n-- sales.Week can be joined with temperature.Week\n-- sales.Year can be joined with markdown.Year\n-- sales.Year can be joined with inflation.Year\n-- sales.Year can be joined with holiday.Year\n-- sales.Year can be joined with fuelprice.Week\n-- sales.Year can be joined with temperature.Year\n
'''


#################Reasoning based##############################

##The style in which the answers to be generated for reasoning based questions(e.g. why did sales go down)
reasoning_style = """The reasoning based answers should consist of three sections:
1.calculations - In this section you must include the step by step process to analyze the question. In your analysis you must identify the metric and the corresponding factors that impact the metric by referring to the information in <relevant_factors></relevant_factors> tag. You must show all the calculations you have done in this section
2.factor_contribution - This section should have the information on how much each of the factors have impacted the metric by (a). showing the % decrease/increase in factor A resulted in %decrease/increase in metric B, (b). The correlation of the factors with the metric. Donot include any claculations in this sections"""

## basic arithmetric operations to be added to prompt for grounding LLM in mathematical tasks
arith_ops = """Subtraction  of 180000 from 225000 is 225000-180000, which is 45000\nPercent decrease from 18888 to 12220 is (18888-12220)*100/12220, which is 6668*100/12220, which is 54%\nAddition of 2987 with 4567 is 2987+4567, which is 7554\nsales for week 1 is 10 and sales for week 3 is 15.5, so sales increased from week 1 to week 3\nsales for week 10 is 20 and sales for week 20 is 12, so sales decreased from week 10 to week 20"""

# Create directories if they don't exist
def setup_directories():
    """Create necessary directories if they don't exist"""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(META_DIR, exist_ok=True)
    os.makedirs(CHAT_DIR_LOCAL, exist_ok=True)
    os.makedirs(INDEX_DIR, exist_ok=True)
    #os.makedirs(DB_PATH, exist_ok=True)

# Print environment info for debugging
def print_environment_info():
    """Print current environment configuration"""
    env_type = "Lambda" if is_lambda_environment() else "Local"
    print(f"Running in {env_type} environment")
    print(f"Home Directory: {HOME_DIR}")
    print(f"Data Directory: {DATA_DIR}")
    print(f"Meta Directory: {META_DIR}")

# Optional: Initialize directories when config is imported
setup_directories()
