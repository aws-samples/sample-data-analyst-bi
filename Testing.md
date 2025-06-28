Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

# Customizing Generation

Effective extraction of insights from relational databases depends fundamentally on how efficiently a model translates natural language questions into SQL or Python queries for visualization. Equally important is improving response times for frequently asked questions.
This guide outlines various configuration options and techniques to customize code generation to meet your specific requirements, ensuring both accuracy and performance when interfacing with your database systems.


## Generation Configuration

Configure generation behavior through several parameters:


### Parameters set in cdk

Parameters influencing the SQL generation quality and also the response time which are to be set in the cdk.json
1. **Model selection** -  Test with different generation models to identify the right model for the usease. The bigger the model, the accuracy of the SQL generated may improve, however it may also increase the response time.
2. **Approach** -  Strat with zero_shot (set approach = "zero_shot") to establish a baseline and then try eewshot startegy (set set approach = "few_shot"). With fewshot strategy, the size of the input prompt would increase, which may impact the response time
3. If you use fewshot strategy, then test with different embedding models(set the paremeter embedding_model_id) 
4. Metadata is a key factor which determines the accuracy of the SQL generated. Set metadata_is_meta = true and provide the correct s3 keys where the metadata files are stored. Adding metadata to the prompt will provide the the relevant context regarding business nuances and help in improving the accuracy of SQL generated. At the same time, the  the sze  the prompt size will increase and may impact the response time

The following parameters which impact the SQL quality and response time can be set in the cdk.jso
```yaml
cdk.json:
  # Model selection and parameters
  "sql_model_id": "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
  "embedding_model_id": "cohere.embed-english-v3",
  "chat_model_id": "us.anthropic.claude-3-5-haiku-20241022-v1:0",
  "approach": "few_shot",
  "metadata_is_meta": true,
  "metadata_table_meta": "schema/student_club_tables.xlsx",
  "metadata_column_meta": "schema/student_club_columns.xlsx",
  "metadata_metric_meta": "schema/student_club_metrics.xlsx",
```
While Anthropic Claude 3.7 can generate SQL accurately relatively to Anthropic Claude Sonnet 3.0, the time taken to generate the SQL in case of Anthropic Claude 3.7 can be slightly more than that of Anthropic Claude Sonnet 3.0


### Parameters set in UI config
There are some parameters which can be set in the following path  - streamlit/UI/config.py

1. **Table Filter** - This parameter is used to determine whether a LLM is to be invoked to select the relevant tables for a question or use all tables from the schema for generating the SQL. If all tables are to be selected, then the LLM is not invoked, resulting in improving the response time. Valid values - ["all", "relevant"]
- `table_selection`: "all" 

2. **Plot model** -  The LLM used to generate a python query to generate plots can be set in the config.py
- `plot_model_id`: "anthropic.claude-3-sonnet-20240229-v1:0"

3. **Caching** - The system uses a approval based caching mechanism where the SQL if approved by the user, then the SQL and the vector embedding of the question are transferred to the cache. In the next run , if the same question is asked by the user, then the SQL is retrieved rom the cache, executed in the database and results returned to the user. In this case, no LLM calls are made, thus improving the response time. The system compares the vector embeddings of the question asked by the user with the vector embeddings of the question stored in the cache and if the similarity score is greater than equal to the threshold, the SQL is retrieved. This approach of caching a question and SQL also helps to automate the creation of fewshot examples in the vector db. Set the threshold parameter
- `cache_thresh`: 0.95 

```bash
N.B. The caching of SQL based on approval from user is currently supported only for questions pertaining to non-plotting types
```

### Parameters set in datanalyst lambda

The data-analyst lambda function receives user questions and classifies them into pre-defined entity types. It retrieves database schema information if not provided, then invokes the querybot lambda to generate appropriate SQL for the query. After executing the SQL against the database, it leverages an LLM to transform the technical results into natural language responses that address the user's question. Based on the identified intent type, it may further utilize an LLM to generate Python visualization code to complement the textual response. 

1. **Intent Identification** - The system classifies user questions into one of three distinct intent categories:
    (A). Greetings Intent - General salutations or conversational openers
    (B). SQL-based Intent - Queries requiring database operations
    (C). Visualization Intent - Requests for graphical data representation
    Intent classification is performed within the data-analyst lambda function using an LLM (Large Language Model) call with a specialized prompt. The current system architecture supports processing questions with a single intent type only. Multi-intent queries are not yet supported.

- `Prompt Path -  data-analyst/scripts/query_db/prompt_config_clv3.py`

```yaml
intent_prompt:
You are an expert data analyst who will perform the following tasks:
- Evaluate if the question can be answered using SQL and/or data visualization by analyzing the provided SQL schema in <schema></schema> tags.
- Do not generate any SQL queries.
- Stop immediately after </answer> tag with no additional text.

<schema>
{schema_str}
</schema>

Response Format:
Your response MUST follow this EXACT format with no deviations or additional text:
<question>
The question asked by the user
</question>
<answer>
EXACTLY ONE of these three options:
- "YesSQL" - For questions answerable with SQL alone
- "YesPlot" - For questions requiring SQL + visualization
</answer>

Examples:
<question>
What are the total sales for store 100?
</question>
<answer>
YesSQL
</answer>

<question>
What are the total sales for store 100?
</question>
<answer>
YesSQL
</answer>

<question>
show me the linechart  of the sales of store 100
</question>
<answer>
YesPlot
</answer>

<question>
show me the trend  of the sales of store 100
</question>
<answer>
YesPlot
</answer>

Important Rules:
1. Never generate SQL queries
2. Never add any text after the </answer> tag
3. Never include explanations or additional context
4. Always maintain the exact tag structure
```

2. **Plot generation** - When a question is received that requests a visual representation (identifiable by terms such as "barchart," "linechart," etc.), our system follows a multi-step process. First, the intent identification mechanism classifies the question as having a visualization intent. Next, the SQL generation component creates an appropriate SQL query, which is then executed to retrieve the necessary data from the database. Subsequently, the system calls the generate_plots visualization method. This method utilizes a specific prompt to invoke a Large Language Model (LLM), which produces Python code. This code is then executed to generate the requested visual representation.

- `Prompt Path -  data-analyst/scripts/query_db/prompt_config_clv3.py`

```yaml
plotting_tempv3:
You are an expert python coder. You are good at writing python code to create different types of plots. Follow the instructions in the <instructions> tag to create python code for generating the plot asked by the user. A sample of actual data on which the plot is to be generated is given in the <actual_data_sample> tag.
Donot apply filters to the data, the data is already filtered.

Given below is the path to the data you should load
<data_path>
{file_path}
</data_path>

Given below is the sample of the actual data which contains all the required columns to create the plot
<actual_data_sample>
{sample}
</actual_data_sample>

Some examples are given in the <example> tag on how to interpret the data and create plots.
<examples>
{ex}
</examples>

Some rules to be followed while plotting are given below:
<plotting_rules>
1.In the x axis, the x tick values should be rotated by 90 degrees
2.while plotting grouped barcharts, the barwidth should be added to the numeric number
</plotting_rules>

<instructions>
(1).Your job is to create plots on the data given in the <actual_data_sample> tag corresponding to the question passed by the user.
(2).Think step by step - follow the instructions given below to generate charts
(3).Create a python function - load the data from the path given inside <data_path> tag.
(4).Import all the required libraries inside the python function
(5).Refer to the examples in the the <examples>tag if available for guidance
(6).Follow the plotting rules given in the <plotting_rules> tag
(7).The python function that you create should return the figure
(8).The plots should be in the same figure plot and use different color codes to represent different entities
(9).After the function definition, assign the relevant data filenames to appropriate variables
(10).Call the python function after the end of the function definition with the filename variables 
(11).Collect the returned value from the function call in a variable named "plot_out". Donot deviate from this
(12).If the data is not available, then donot plot and return empty figure
(13).Return your the python function definition and function call inside the <answer> tag and your step by step reasoning to construct python defintion in the <explanation> tag
</instructions>

IMPORTANT - 
(1). You should import all the required libraries such as matplotlib, pandas inside the python function definition
(2). Before creating the python function, check what columns are available for the data in <actual_data_sample> tag. You should not filter the data for any values inside the function definition
(3). Only use columns available in <actual_data_sample> tag to perform any data transformations needed inside the pythom function definition. You should not refer to any columns not available in the data inside <actual_data_sample> tag
(4). Just reminding you that your job is to create a python function to generate plot. No filters are required on the data
```

```bash
N.B. For invoking Bedrock LLMs used in the data-analyst lambda function from a specific region , set AWS_REGION in the config.py of data-analyst lambda function in the following path  - data-analyst/scripts/query_db/config.py
```

### Parameters set in query bot lambda

The Query Bot Lambda function, invoked by the Data Analyst Lambda, loads metadata from S3 and incorporates it into the schema. It then leverages LLMs to analyze user questions and identify only the relevant tables(this step is optional and contolled by the 'table_selection' parameter ) needed for answering specific queries. Finally, it invokes another LLM to generate the appropriate SQL query based on the user's question and the filtered schema information.

1. **SQL generation**  - The querybot lambda is responsible for the generation of SQL by invoking LLM configured in the cdk. The prompt templates are available in the querybot -> scripts -> prompts.py. System prompts and sql prompts for both zeroshot and fewshot can be customized dependingon the usecase

- `Prompt Path - querybot/scripts/prompts.py`
  
System prompt - 
 ```yaml
BEDROCK_SYS_PROMPT: 
You are an expert SQL query generator.
Given an input question and a database schema within the <schema></schema> tag, create a precise, syntactically correct and efficient SQL query.
please follow the instructions while generating the sql:
    1.Please generate SQL compatible with {sql_database} database.
    2.Ensure that the generated SQL select statement includes all relevant factors including identifier or filter columns mentioned in the input question.
    3.Always include identifier columns in the SELECT clause when they are used in WHERE conditions.
```

Zeroshot prompt - 
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
Fewshot prompt - 
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

2. **Model hyperparameters** - The LLM's hyperparameters can also influence the accuracy of SQL. Hyperparameter configuration for some models are show below:

- `Path - querybot/scripts/config.py`

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

3. **Retrieval score threshold** -  In the fewshot setting, the system will perform a semantic similarity match between the embeddings of the question asked by the user with that of the questions available in the vector store. Relevant examples whose scores exceed the threshold are selected to be added in the prompt. 

- `Path - querybot/scripts/config.py`

- `AOSS_RELEVANCE_THRESHOLD`: 0.75

```bash
N.B. For invoking Bedrock LLMs used in the query bot lambda from a specific region , set AWS_REGION in the config.py of data querybot lambda function in the following path - querybot/scripts//config.py
```

# Setting up the cache/fewshot examples
The vector store is created after the cdk deployment is done. Post that, the table should be created inside the vector store. This table will store the fewshot examples and the frequently asked questions.
The question, the embeddings of the question, SQL query  and the explanation of the SQL query are stored in the vector store. The question,the SQL and the explanation are added to the prompt. The explanation helps the LLM to learn how to construct the SQL from the question.
The steps given below detail out on how to create the table inside the vector store and 
The vector store is used for storing the fewshot examples. 

```bash
1. Copy the tools folder (data utilities) available inside the parent directory to a Sagemaker notebook instance/EC2(The Sagemaker instance/EC2 should be in the same VPC and the security group as the vector database.The subnet choosen must be in a private egress subnet linked to a NAT gateway)
2. The configurations for setting up cache and ingesting fewshot examples are in the config.py inside the tools folder -  the embedding model name, the configuration for the vector database etc. Set these values as required
3. Open the create_cache_fshot.ipynb and runn the cells
3. In a terminal, run pip install -r requirements.txt to install the required dependencies 
4. Run python create_cache.py to create the cache table in the vector database
5. Store the fewshot examples inside "fshot_data" folder following the format given in the examples.xlsx.  Run the cell main() to ingest the examples in the vector store
```
# Migrating sqlite db to RDS Postgres
```bash
User can migrate the data from sqlite to RDS Postgres using the utitlies available inside the tools/ directory

1. Ensure that the RDS database connection parameters are correctly set in the tools/config.py inside the tools folder
2. Ensure that the path to the sqlitedb is set in the sqlite_dir parameter in tools/config.py
3. Open a terminal in sagemaker and type (1).pip install -r requirements.txt and then (2). python migrate_data_sqlite_postgres.py and select "all" when prompted
4. The sqlite tables will be migrated to RDS postgres
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
| **Timeout Error** | Goto the logs in the application bucket and check the total response time. If it is more than 29 secs, then the issue is with the API Gateway timeout. The default quota for API Gateway is set to 29 secs. A service ticket can be raised in the AWS console to increase it to 80000 msecs. Go to service quotas--> API Gateway. Maximum integration timeout in milliseconds" and set the "Increase quota value" to 80000 ms.This is auto-approved. Wait for an half an hour and then go to the API Gateway service from the console. Go to your API --> Resources --> POST--> Integration Request. Click on Edit and change the "Integration timeout" to the one that you applied in your quota request. Once done, click on Deploy API and select the stage. |
| **Failed to generate SQL** | (1). Check if all the LLMs used in the asset are activated in Bedrock. (2).Check if the lambda function is able to connect to the vector database and the api database. This can be validated in the cloudwatch logs |
| **AccessDeniedException when calling the InvokeModel operation** |Resolution is same as in the previous issue |
| **Fewshot examples not getting added to prompt** | You will not see an error, however if you use one embedding model for populating the vector database and another embedding model to generate the embeddings for incoming question, then no data will be retrieved from the vector database and added to the prompt. This can be validated in the cloudwatch logs of the querybot lambda |
  **Other Issues**  | Check the cloudwatch logs of both the lambda functions or check the logs stored in the S3 bucket created by the cdk deployment



