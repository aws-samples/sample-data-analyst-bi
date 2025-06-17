BEDROCK_SYS_PROMPT = """
You are an expert SQL query generator.
Given an input question and a database schema within the <schema></schema> tag, create a precise, syntactically correct and efficient SQL query.
please follow the instructions while generating the sql:
    1.Please generate SQL compatible with {sql_database} database.
    2.Ensure that the generated SQL select statement includes all relevant factors including identifier or filter columns mentioned in the input question.
    3.Always include identifier columns in the SELECT clause when they are used in WHERE conditions.

"""


BEDROCK_ZS_SQL_PROMPT = """
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

Put your answer in <sql></sql> tag."""


BEDROCK_ZS_METADATA_SQL_PROMPT = """
The database schema below contains the following fields:
- Table name
- Table description
- Column names
- Column descriptions
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

Put your answer in <sql></sql> tag."""

CODELLAMA_ZS_SQL_PROMPT = """
Given a database schema in <schema></schema> and a question text in <question></question>, create a syntactically correct and efficient SQL query.
Important: Please generate SQL compatible with {sql_database} database.

<schema>
{schema}
</schema>
NOTE: The schema above is provided in |<table> : <column 1>, <columns 2>, . . ., <columns n> | format.

<question>
{question}
</question>


### SQL query:
{query}
"""

BEDROCK_FS_SQL_PROMPT = """
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

Put your answer in <sql></sql> tag."""

BEDROCK_FS_METADATA_SQL_PROMPT = """
The database schema below contains the following fields:
- Table name
- Table description
- Column names
- Column descriptions
- Column data types
- Key information

Given the database schema within the <schema></schema> tags 

<schema>
{schema}
</schema>

and the following example pairs of question and sql queries given within the <example></examples> tags

<examples>
{examples}
</examples>

generate a SQL statement for the question within the <question></question> tags

<question>
{question}
</question>

put your answer in <sql></sql> tag."""


FS_EXAMPLE_STRUCTURE = """
<example>
    <question>
        {question}
    </question>
    <sql>
        {sql}
    </sql>
    <expl>
        {expl}
    </expl>
    <gen_q>
        {gen_q}
    </gen_q>
<example>
"""
filter_tables_system_prompt ="""
You are an expert in database schema analysis and query interpretation. 
Your primary role is to identify the relevant tables from a given database schema 
that are necessary to answer a user's question. Note: Do not generate explanation"""

query_text_tab_tempv3 = """
Given a database schema and a question, identify the relevant tables needed to answer the question.

Input Format:
1. Database schema will be provided within <schema></schema> tags and contains:
    - Table names
    - Table descriptions
    - Column names and descriptions
    - Column data types
    - Key information
2. Question will be provided within <question></question> tags

Output Format:
- Return answer within <tables_list></tables_list> tags
- Format as a Python list of table names (e.g., ['table1', 'table2'])
- Can return single table (e.g., ['table1']) or multiple tables as needed

Example Outputs:
<tables_list>
['out1', 'out2', 'out3']
</tables_list>
<tables_list>
['out1']
</tables_list>

Schema:
<schema>
{schema}
</schema>

Question:
<question>
{question}
</question>
"""

LLM_ZS_PROMPTS = {
    "anthropic.claude-v2:1": BEDROCK_ZS_SQL_PROMPT,
    "anthropic.claude-instant-v1": BEDROCK_ZS_SQL_PROMPT,
    "anthropic.claude-3-sonnet-20240229-v1:0": BEDROCK_ZS_SQL_PROMPT,
    "anthropic.claude-3-haiku-20240307-v1:0": BEDROCK_ZS_SQL_PROMPT,
    "anthropic.claude-3-5-sonnet-20240620-v1:0":BEDROCK_ZS_SQL_PROMPT,
    "anthropic.claude-3-5-sonnet-20241022-v2:0":BEDROCK_ZS_SQL_PROMPT,
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0":BEDROCK_ZS_SQL_PROMPT,
    "us.anthropic.claude-3-5-haiku-20241022-v1:0":BEDROCK_ZS_SQL_PROMPT,
    "us.anthropic.claude-3-7-sonnet-20250219-v1:0":BEDROCK_ZS_SQL_PROMPT,
    "ic-deepseek-r1-distill-llama-70b":BEDROCK_ZS_SQL_PROMPT,
    "amazon.nova-micro-v1:0":BEDROCK_ZS_SQL_PROMPT,
    "amazon.nova-lite-v1:0":BEDROCK_ZS_SQL_PROMPT,
    "amazon.nova-pro-v1:0":BEDROCK_ZS_SQL_PROMPT,
    "us.meta.llama3-3-70b-instruct-v1:0":BEDROCK_ZS_SQL_PROMPT,
    "hf_codellama": CODELLAMA_ZS_SQL_PROMPT
}

LLM_FS_PROMPTS = {
    "anthropic.claude-v2:1": BEDROCK_FS_SQL_PROMPT,
    "anthropic.claude-instant-v1": BEDROCK_FS_SQL_PROMPT,
    "anthropic.claude-3-sonnet-20240229-v1:0": BEDROCK_FS_SQL_PROMPT,
    "anthropic.claude-3-haiku-20240307-v1:0": BEDROCK_FS_SQL_PROMPT,
    "anthropic.claude-3-5-sonnet-20240620-v1:0":BEDROCK_FS_SQL_PROMPT,
    "anthropic.claude-3-5-sonnet-20241022-v2:0":BEDROCK_FS_SQL_PROMPT,
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0":BEDROCK_FS_SQL_PROMPT,
    "us.anthropic.claude-3-5-haiku-20241022-v1:0":BEDROCK_FS_SQL_PROMPT,
    "us.anthropic.claude-3-7-sonnet-20250219-v1:0":BEDROCK_FS_SQL_PROMPT,
    "ic-deepseek-r1-distill-llama-70b":BEDROCK_FS_SQL_PROMPT,
    "amazon.nova-micro-v1:0":BEDROCK_FS_SQL_PROMPT,
    "amazon.nova-lite-v1:0":BEDROCK_FS_SQL_PROMPT,
    "amazon.nova-pro-v1:0":BEDROCK_FS_SQL_PROMPT,
    "us.meta.llama3-3-70b-instruct-v1:0":BEDROCK_FS_SQL_PROMPT,
}

LLM_PROMPTS_FINAL = {
    "anthropic.claude-v2:1": "\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "anthropic.claude-instant-v1": "\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "anthropic.claude-3-sonnet-20240229-v1:0": "\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "anthropic.claude-3-haiku-20240307-v1:0": "\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "anthropic.claude-3-5-sonnet-20240620-v1:0":"\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "anthropic.claude-3-5-sonnet-20241022-v2:0":"\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0":"\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "us.anthropic.claude-3-5-haiku-20241022-v1:0":"\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "us.anthropic.claude-3-7-sonnet-20250219-v1:0":"\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "amazon.nova-micro-v1:0":"\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "amazon.nova-lite-v1:0":"\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "amazon.nova-pro-v1:0":"\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "us.meta.llama3-3-70b-instruct-v1:0":"\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "hf_codellama": "{sql_prompt}"
}

BR_IP_SYS_PROMPT = """
You are a highly skilled data engineer with expertise in SQL database.
"""

BR_SQL_INTERPRETATION = """The user asked the question:
<question>
{question}
<question>

The following is the result table of the query:
<result>
{result}
</result>

Your task is to briefly interpret and summarize the result table in a human-readable format.
Please try not to use terms like table, row, column, etc. in your output as it is intended for non-technical users.
Put your answer in <response></response> tag.
"""


BR_IP_SYS_PROMPT = """
You are a highly skilled data engineer with expertise in SQL database.
"""

BR_SQL_INTERPRETATION = """The user asked the question:
<question>
{question}
<question>

The following is the result table of the query:
<result>
{result}
</result>

Your task is to briefly interpret and summarize the result table in a human-readable format.
Please try not to use terms like table, row, column, etc. in your output as it is intended for non-technical users.
Put your answer in <response></response> tag.
"""

LLM_IP_PROMPTS = {
    "anthropic.claude-v2:1": BR_SQL_INTERPRETATION,
    "anthropic.claude-instant-v1": BR_SQL_INTERPRETATION,
    "anthropic.claude-3-sonnet-20240229-v1:0": BR_SQL_INTERPRETATION,
    "anthropic.claude-3-haiku-20240307-v1:0": BR_SQL_INTERPRETATION,
    "anthropic.claude-3-5-sonnet-20240620-v1:0": BR_SQL_INTERPRETATION,
    "anthropic.claude-3-5-sonnet-20241022-v2:0": BR_SQL_INTERPRETATION,
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0": BR_SQL_INTERPRETATION,
    "us.anthropic.claude-3-5-haiku-20241022-v1:0": BR_SQL_INTERPRETATION,
    "us.anthropic.claude-3-7-sonnet-20250219-v1:0": BR_SQL_INTERPRETATION,
    "ic-deepseek-r1-distill-llama-70b": BR_SQL_INTERPRETATION,
    "amazon.nova-micro-v1:0":BR_SQL_INTERPRETATION,
    "amazon.nova-lite-v1:0":BR_SQL_INTERPRETATION,
    "amazon.nova-pro-v1:0":BR_SQL_INTERPRETATION,
    "us.meta.llama3-3-70b-instruct-v1:0":BR_SQL_INTERPRETATION,
}

LLM_IP_PROMPTS_FINAL = {
    "anthropic.claude-v2:1": "\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "anthropic.claude-instant-v1": "\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "anthropic.claude-3-sonnet-20240229-v1:0": "\n\nHuman: {sql_prompt} \nAssistant:",
    "anthropic.claude-3-haiku-20240307-v1:0": "\n\nHuman: {sql_prompt} \nAssistant:",
    "anthropic.claude-3-5-sonnet-20240620-v1:0": "\n\nHuman: {sql_prompt} \nAssistant:",
    "anthropic.claude-3-5-sonnet-20241022-v2:0": "\n\nHuman: {sql_prompt} \nAssistant:",
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0": "\n\nHuman: {sql_prompt} \nAssistant:",
    "us.anthropic.claude-3-5-haiku-20241022-v1:0": "\n\nHuman: {sql_prompt} \nAssistant:",
    "us.anthropic.claude-3-7-sonnet-20250219-v1:0": "\n\nHuman: {sql_prompt} \nAssistant:",
    "amazon.nova-micro-v1:0": "\n\nHuman: {sql_prompt} \nAssistant:",
    "amazon.nova-lite-v1:0": "\n\nHuman: {sql_prompt} \nAssistant:",
    "amazon.nova-pro-v1:0": "\n\nHuman: {sql_prompt} \nAssistant:",
    "us.meta.llama3-3-70b-instruct-v1:0": "\n\nHuman: {sql_prompt} \nAssistant:",
}

BEDROCK_RECTIFIER_PROMPT = """You generated a SQL command in the <sql><sql> tag
for a question in <question></question> tag and then got the syntax <error></error> tag as follows:

<question>
{question}
</question>

<sql>
{sql_cmd}
</sql>

<error>
{syntax_error}
</error>

Given the database schema within the <schema></schema> tags 

<schema>
{schema}
</schema>

you need to corret the SQL command and rewrite it syntactically correct.
Put your answer in <sql></sql> tag.
"""

LLM_RECTIFIER_PROMPTS = {
    "anthropic.claude-v2:1": BEDROCK_RECTIFIER_PROMPT,
    "anthropic.claude-instant-v1": BEDROCK_RECTIFIER_PROMPT,
    "anthropic.claude-3-sonnet-20240229-v1:0": BEDROCK_RECTIFIER_PROMPT,
    "anthropic.claude-3-haiku-20240307-v1:0": BEDROCK_RECTIFIER_PROMPT,
    "anthropic.claude-3-5-sonnet-20240620-v1:0": BEDROCK_RECTIFIER_PROMPT,
    "anthropic.claude-3-5-sonnet-20241022-v2:0": BEDROCK_RECTIFIER_PROMPT,
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0": BEDROCK_RECTIFIER_PROMPT,
    "us.anthropic.claude-3-5-haiku-20241022-v1:0": BEDROCK_RECTIFIER_PROMPT,
    "us.anthropic.claude-3-7-sonnet-20250219-v1:0": BEDROCK_RECTIFIER_PROMPT,
    "ic-deepseek-r1-distill-llama-70b": BEDROCK_RECTIFIER_PROMPT,
    "amazon.nova-micro-v1:0":BEDROCK_RECTIFIER_PROMPT,
    "amazon.nova-lite-v1:0":BEDROCK_RECTIFIER_PROMPT,
    "amazon.nova-pro-v1:0":BEDROCK_RECTIFIER_PROMPT,
    "us.meta.llama3-3-70b-instruct-v1:0":BEDROCK_RECTIFIER_PROMPT,
}

LLM_RECTIFIER_PROMPTS_FINAL = {
    "anthropic.claude-v2:1": "\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "anthropic.claude-instant-v1": "\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "anthropic.claude-3-sonnet-20240229-v1:0": "\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "anthropic.claude-3-haiku-20240307-v1:0": "\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "anthropic.claude-3-5-sonnet-20240620-v1:0": "\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "anthropic.claude-3-5-sonnet-20241022-v2:0": "\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0": "\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "us.anthropic.claude-3-5-haiku-20241022-v1:0": "\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "us.anthropic.claude-3-7-sonnet-20250219-v1:0": "\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "amazon.nova-micro-v1:0": "\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "amazon.nova-lite-v1:0": "\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "amazon.nova-pro-v1:0": "\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
    "us.meta.llama3-3-70b-instruct-v1:0": "\n\nHuman: {sys_prompt} \n{sql_prompt} \nAssistant:",
}
