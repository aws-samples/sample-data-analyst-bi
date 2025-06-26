Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

# Customizing Generation

Effective extraction of insights from relational databases depends fundamentally on how efficiently a model translates natural language questions into SQL or Python queries for visualization. Equally important is improving response times for frequently asked questions.
This guide outlines various configuration options and techniques to customize code generation to meet your specific requirements, ensuring both accuracy and performance when interfacing with your database systems.


## Generation Configuration

Configure generation behavior through several parameters:


### Parameters set in cdk

Parameters influencing the SQL generation quality and also the response time which are to be set in the cdk.json
1. Model selection -  Test with different generation models to identify the right model for the usease. The bigger the model, the accuracy of the SQL generated may improve, however it may also increase the response time.
2. Approach -  Strat with zero_shot (set approach = "zero_shot") to establish a baseline and then try eewshot startegy (set set approach = "few_shot"). With fewshot strategy, the size of the input prompt would increase, which may impact the response time
3. If you use fewshot strategy, then test with different embedding models(set the paremeter embedding_model_id) 
4. Metadata is a key factor which determines the accuracy of the SQL generated. Set metadata_is_meta = true and provide the correct s3 keys where the metadata files are stored. Adding metadata to the prompt will provide the the relevant context regarding business nuances and help in improving the accuracy of SQL generated. At the same time, the  the sze  the prompt size will increase and may impact the response time

The following parameters which impact the SQL quality and response time can be set in the cdk.jso
```yaml
cdk.json:
  # Model selection and parameters
  "sql_model_id": "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
  "embedding_model_id": "cohere.embed-english-v3",
  "approach": "few_shot",
  "metadata_is_meta": true,
  "metadata_table_meta": "schema/student_club_tables.xlsx",
  "metadata_column_meta": "schema/student_club_columns.xlsx",
  "metadata_metric_meta": "schema/student_club_metrics.xlsx",
```
While Anthropic Claude 3.7 can generate SQL accurately relatively to Anthropic Claude Sonnet 3.0, the time taken to generate the SQL in case of Anthropic Claude 3.7 can be slightly more than that of Anthropic Claude Sonnet 3.0


### Parameters set in UI config
There are some parameters which can be set in the UI/config.py which may impact the response time

1. Table Filter - This parameter is used to determine whether a LLM is to be invoked to select the relevant tables for a question or use all tables from the schema for generating the SQL. If all tables are to be selected, then the LLM is not invoked, resulting in improving the response time. Valid values - ["all", "relevant"]
- `table_selection`: "all" 

2. Caching - The system uses a approval based caching mechanism where the SQL if approved by the user, then the SQL and the vector embedding of the question are transferred to the cache. In the next run , if the same question is asked by the user, then the SQL is retrieved rom the cache, executed in the database and results returned to the user. In this case, no LLM calls are made, thus improving the response time. The threshold compares the vector embeddings of the question asked by the user with the vector embeddings of the question stored in the cache and if the similarity score is greater than equal to the threshold, the SQL is retrieved
- `cache_thresh`: 0.95 

### Parameters set in query bot lambda

1. Prompt  - The querybot lambda is responsible for the generation of SQL by invoking LLMs configured in the cdk. However, the prompt templates are available in the querybot -> scripts -> prompts.py. System prompts and sql prompts for both zeroshot and fewshot can be customized dependingon the usecase
  
 ```yaml
BEDROCK_SYS_PROMPT: 
You are an expert SQL query generator.
Given an input question and a database schema within the <schema></schema> tag, create a precise, syntactically correct and efficient SQL query.
please follow the instructions while generating the sql:
    1.Please generate SQL compatible with {sql_database} database.
    2.Ensure that the generated SQL select statement includes all relevant factors including identifier or filter columns mentioned in the input question.
    3.Always include identifier columns in the SELECT clause when they are used in WHERE conditions.
```

```yaml
BEDROCK_ZS_SQL_PROMPT: 
The database schema below contains the following fields:
- Table name
- Column names
- Column data types
- Key information

Given the database schema within the <schema></schema> tags 

<schema>
{schema}
</schema>

generate a SQL statement for the question within the <question></question> tags:

<question>
{question}
</question>

Put your answer in <sql></sql> tag.
```

```yaml
BEDROCK_FS_SQL_PROMPT:
For each table, you are provided with some or all of the following
    - Table name
    - Column names
    - Column data types
    - Key information

Given the database schema within the <schema></schema> tags 

<schema>
{schema}
</schema>

and the following example pairs of question , sql queries, explanation of the SQL query and a similar question created from the SQL given within the <example></examples> tags

<examples>
{examples}
</examples>

generate a SQL statement for the question within the <question></question> tags

<question>
{question}
</question>
```

2. Model hyperparameters - The LLM's hyperparameters can also influence the accuracy of SQL. These are set inside 
querybot -> scripts -> config.py. Hyperparameter configuration for some models are show below:
```yaml
LLM_CONF:
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
    }
```

3. Retrieval score threshold -  In the fewshot setting, the system will perform a semantic similarity match between the embeddings of the question asked by the user with that of the questions available in the vector store. Relevant examples whose scores exceed the threshold are selected to be added in the prompt. The score can be set inside querybot -> scripts -> config.py

- `AOSS_RELEVANCE_THRESHOLD`: 0.75

# Setting up the cache/fewshot examples
The vector store is created after the cdk deployment is done. Post that, the table should be created inside the vector store. This table will store the fewshot examples and the frequently asked questions.
The question, the embeddings of the question, SQL query  and the explanation of the SQL query are stored in the vector store. The question,the SQL and the explanation are added to the prompt. The explanation helps the LLM to learn how to construct the SQL from the question.
The steps given below detail out on how to create the table inside the vector store and 
The vector store is used for storing the fewshot examples. 

```bash
1. Copy the tools folder (data utilities) available inside the parent directory to a Sagemaker notebook instance/EC2(The Sagemaker instance/EC2 should be in the same VPC and the security group as the vector database.The subnet choosen must be in a private subnet with nat gateway)
2. The tools folder has the configurations -  the embedding model name, the configuration for the vector database etc. Set these values as required
3. Open the create_cache_fshot.ipynb and runn the cells
3. In a terminal, run pip install -r requirements.txt to install the required dependencies 
4. Run python create_cache.py to create the cache table in the vector database
5. Store the fewshot examples inside "fshot_data" folder following the format given in the examples.xlsx.  Run the cell main() to ingest the examples in the vector store
```
# Migrating sqlite db to RDS Postgres
```bash
User can migrate the data from sqlite to RDS Postgres using the utitlies available inside the tools/ directory

1. Ensure that the RDS database connection parameters are correctly set in the config.py inside the tools folder
2. Ensure that the path to the sqlitedb is set in the sqlite_dir parameter in config.py
3. Open a terminal and type  python migrate_data_sqlite_postgres.py and selct "all" once prompted
4. The tables will be migrated to RDS postgres
```

# Monitoring

The solution persists the log of time taken for each step and the error logs in the S3 bucket created through the CDK deployemnt 

## Latency components

The time taken in each step is tored inside the processing_times folder in the application bucket created by the cdk deployment

- **validating Input**: Time taken to validate the input
- **get_cache_entries**: Time taken to check the entires in cache
- **extract Schema**: Time taken to extract the schema from database
- **question_intent**: Time taken to identify whether the question is a SQL based or python or a greeting question
- **sql_generation**: Time taken to generate the SQL
- **sql_execution**: Time taken to execute the SQL
- **sql_re-execution**: Time taken to regenerate the SQL(if it has wrong syntx) and re-execute
- **Normalization**: Time taken to normalize fileter values in the SQL
- **Explanation generation**: Time taken to convert the results from the database to natural language response

- **Total processing time**: The total processing time

## Error logs

1. The error logs are stored in the log_files folder inside the application bucket

2. The logs can also be tracked in the cloudwatch logs of the two lambda functions that are deployed through the cdk deployment

# Troubleshooting Guide

This guide provides solutions for common issues and optimization techniques for the GenAIIDP solution.

## Common Issues and Resolutions

| Issue | Resolution |
|-------|------------|
| **Timeout Error** | Goto the logs in the application bucket and check the total response time. If it is more than 29 secs, then the issue is with the API Gateway timeout. The default quota for API Gateway is set to 29 secs. A service ticket can be raised in the AWS console to increase it to 80 secs |
| **Failed to generate SQL** | (1). Check if all the LLMs used in the asset are activated in Bedrock. (2).Check if the lambda function is able to connect to the vector database and the api database. This can be validated in the cloudwatch logs |
| **AccessDeniedException when calling the InvokeModel operation** |Resolution is same as in the previous issue |
| **Fewshot examples not getting added to prompt** | You will not see an error, however if you use one embedding model for populating the vector database and another embedding model to generate the embeddings for incoming question, then no data will be retrieved from the vector database and added to the prompt. This can be validated in the cloudwatch logs of the querybot lambda |



