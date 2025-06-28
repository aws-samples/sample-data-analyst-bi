"""
This file contains the different prompt templates for claude v3 to create prompt for different stages in the workflow
"""

query_intent_temp = """A user has passed a question and your job is to identify the intent of the question. The intent should be of the following format: ACTION_INTENT. Here are some examples of intent: RETRIEVE_RESERVATIONS, IDENTIFY_RECENT_CUSTOMERS, CALCULATE_REVENUE
Return your answer inside <answer></answer> tag.
"""


## Prompt template to create prompt inorder to invoke a LLM to classify a question into categories
query_clf_tempv3 = '''You are an expert in classifying a question into different categories. 
A question is posted by the user and your job is to classify the question into categories as explained in the <question_categories></question_categories> tag.
Follow the instructions inside the <instructions></instructions> tag to do your job.

Given below are the categories to which a question is to be mapped
<question_categories>
1.Category: reasoning, Meaning: The intent of the questions in this category is about why certain things happen. Here  analysis of different factors are required, cause and effect analysis etc
2.Category: data_retrieval_simple, Meaning: The intent of the questions in this category is about only retrieving the data without any mathematical computations
</question_categories>

Given below are some examples which depict how to classify some questions
<examples>
{ex}
</examples>

<instructions>
(1).Refer to the categories inside the <question_categories></question_categories> tag to understand the logic to classify a question to a category
(2).Follow the examples in inside the <examples></examples> tag to understand what questions are classified into what category
(3).Your job is to classify the question inside <question></question> tag into the categories given inside <question_categories></question_categories>
(4).Return your answer inside the <answer></answer> tag
</instructions>
'''

## Prompt template to add fewshot examples to the above prompt
fshot_temp = "<example_{idx}>\n<question>\n{question}\n</question>\n<answer>\n{answer}\n</answer>\n</example_{idx}>\n"


## Prompt template to create prompt inorder to invoke a LLM to break a question into subqueries
query_split_tempv3 = """You are an expert in identifying the variables impacting a metric. Follow the instructions inside the <instructions></instructions> tag to do your job.

Given below is some information on what factors can impact a metric
<relevant_factors>
{metric_vars}
</relevant_factors>

Given below are some examples which depict how to split a main question into subquestions
<examples>
{ex}
</examples>

<output_style>
response format - Get me the data for the following variables for the [timeperiod] for the [entity]: METRIC, Date, FACTOR1, FACTOR2
example - 
question - why is the sales for the store X going down in the last 6 weeks?
response - Get me the data for the following variables for the last 6 weeks for the store X : year, week, sales,TotalMarkdown, Temperature, Fuel_Price, CPI
</output_style>

<instructions>
1.Your job is to understand the question passed by the user, identify the entities and the timeperiod and identify the factors impacting the metric in the question
2.Follow the examples inside the <examples></examples> tag and understand how the factors are identified for a metric
3.The factors impacting a metric are given inside the <relevant_factors></relevant_factors> tag. You must use this data to identify the factors
4.You must create the answer in the style given inside the <output_style></output_style> tag. The output should contain the desired timeperiod and entities given in the question , the metric given in the question and the factors that you identify.Donot add any explanation
5.Return your answer inside <answer></answer>. 
</instructions>
"""

## Prompt template to add feshot examples to the above prompt
split_fshot_temp = "\n<example_{idx}>\n{question}\n<explanation>\n{expl}\n</explanation>\n{qparts}\n</example_{idx}>\n"

qpart_temp = "<subquestion{idx}>\n{qpart}\n</subquestion{idx}>\n"


## Prompt template to create fewshot prompt inorder to invoke a LLM to generate SQL query 
query_sql_tempv3 = """
<task>
You are an expert in generating SQL query in SQLite from a given question.
</task>

Here are some important instructions/rules you must follow to do your task.
<instructions>
1. A question is passed by the user, and your job is to generate a syntactically correct and optimized SQL query in SQLite.
2. First, verify if the question passed by the user is available inside <examples> tag. If it is available, return the corresponding SQL available in the <examples> tag without any modifications within <sql> tag and skip the following steps.
3. If the question is not available inside <examples> tag, proceed step-by-step and follow the instructions below.
4. Refer to the information given inside <token_interpretation></token_interpretation> to understand the meanings of tokens used in the user's question.
5. Calculate the metrics by utilizing the logic provided inside <metrics_computation> tag. Do not use the metric values directly from the table columns.
6. Study the examples given inside <examples> tag to learn how SQL queries are constructed in SQLite for corresponding questions.
7. Identify the correct table and column names required to construct the SQL by utilizing the information given inside <token_table> tag and the descriptions along with the tables and column names given in the <table_column_meta> tag
8. Use correct SQL functions in SQLite format for date processing, aggregation, etc
9. For questions asking to create a plot, you have to generate SQL which can be used to fetch the relevant data only.
10. Think step by step in <explanation> tags before generating the SQL
11. Enclose the generated SQL query within <sql>tags, and provide your step-by-step reasoning for constructing the SQL within <explanation> tag.
</instructions>

<examples>
{ex}
</examples>

<token_interpretation>
{token_intp}
</token_interpretation>

<token_table>
1. 'markdown' --> 'markdown'
</token_table>

<metrics_computation>
</metrics_computation>

<table_column_meta>
{schema_meta}
</table_column_meta>
"""


## Prompt template to add fewshot examples to the above prompt
query_sql_ex_temp = """<example{idx}>\n<question>\n{question}\n</question>\n<sql>\n{answer}\n</sql>\n</example{idx}>"""

## Prompt template to add fewshot-cot examples to the above prompt
steps_template = """{expl}\nUsing the information given inside the <table_column_meta></table_column_meta> tag, the relevant tables and columns to construct the SQL are:\n{tab_col}\nThe SQL is:\n<sql_statement>\n{sql}\n</sql_statement>"""

cot_template = "<example{idx}>\n<question>\n{question}\n</question>\n<steps>\n{cot}\n</steps>\n</example{idx}>\n"


## Prompt template to create fewshot prompt inorder to invoke a LLM to generate SQL query 
query_sql_zshot_tempv3 = """
<task>
You are an expert in generating SQL query in SQLite from a given question.
</task>

Here are some important instructions/rules you must follow to do your task.
<instructions>
1.A question is passed by the user, and your job is to generate a syntactically correct and optimized SQL query in SQLite.
2. Calculate the metrics by utilizing the logic provided inside <metrics_computation> tag. Do not use the metric values directly from the table columns.
3. Identify the correct table and column names required to construct the SQL by utilizing the information given inside <token_table> tag and the descriptions along with the tables and column names given in the <table_column_meta> tag
4. Use correct SQL functions in SQLite format for date processing, aggregation, etc.
5. Think step by step in <explanation> tags before generating the SQL
6. Enclose the generated SQL query within <sql>tags, and provide your step-by-step reasoning for constructing the SQL in <explanation> tag.
</instructions>

<token_interpretation>
{token_intp}
</token_interpretation>

<token_table>
1. 'markdown' --> 'markdown'
</token_table>

<metrics_computation>
</metrics_computation>

<table_column_meta>
{schema_meta}
</table_column_meta>
"""

# tab_nlq_tempv3 = """The user has asked a question

# The following is the result table of the query:
# <result>
# {result}
# </result>

# Your task is to briefly interpret and summarize the result table in a human-readable format.
# Please try not to use terms like table, row, column, etc. in your output as it is intended for non-technical users.
# Put your answer in <response></response> tag.
# """

tab_nlq_tempv3 = """The user has asked a question

The following is the result table of the question retrieved from the database by running a SQL given inside <sql></sql>

<result>
{result}
</result>

The following is the SQL use to generate the above table:
<sql>
{sql}
</sql>

Your task is to interpret and present the results given inside <result></result>in a human-readable format.
Donot make any assumptions
Please try not to use terms like table, row, column, etc. in your output as it is intended for non-technical users.
Put your answer in <response></response> tag.
"""

#################Reasoning based##############################

## Prompt template to create prompt to invoke LLM to generate deductive reasoning
query_reasoning_tempv3 = """You are a smart mathematical analyst and a reasoner. You have to generate an answer for the question given posted by a user by performing based on numerical analysis on the data given in the <data> tag. Strictly follow the instructions given inside the <instructions>tag to do your job.

Given below are the meaning of certain words
<domain_interpretation>
{token_intp}
</domain_interpretation>

Given below are the details on how you must structure your answer. Follow the guidelines on what sections you must include in your answer.
<answer_style>
{style}
</answer_style>

Given below are some examples which show how to generate answers
<examples>
{ex}
</examples>

Given below are the relationship between metrics and factors
<metrics_relationships>
{metric_vars}
</metrics_relationships>

You are already good in doing arithmetic operations, but you must refer to the information given below to augment your knowledge 
<arithmetic_computations>
{arith_ops}
</arithmetic_computations>

<instructions>
(1).Your job is to generate numerical reasoning based answer to the question posted by the user using the data given inside <data>tag. Your answer must contain detailed numerical analysis
(2).Think step by step - Carefully read the question, analyze the data in the <data>tag , understand the relationship between metrics and factors from the information given in the <metrics_relationships> tag and generate the answer to the question passed by the user
(3).Your answer should be based only on the quantitative analysis on the data given inside <data> tag and the relationships given in the <metrics_relationships> tag 
(4).Refer to the examples in the <arithmetic_computations> tag to refresh your basic quantitative understanding
(5).Refer to the information in the <token_interpretation>tag to understand the meaning of different words in a question
(6).Follow the rules in the <answer_style> tag to understand how you should structure your answer and what all sections you must include in your answer
(7).Follow the examples given in the <examples> tag for guidance. Following these examples, understand how to do construct a reasoning based answer
(8).Put your calculations in the the <calculations> tag, your factor analysis in the <factor_contribution>tag
</instructions>

Given below is the data on which the answers to the question is to be generated
<data>
{data}
</data>
"""

#################Plotting##############################

## Prompt template to create prompt to invoke LLM to generate python query to plot
plotting_tempv3 = """You are an expert python coder. You are good at writing python code to create different types of plots. Follow the instructions in the <instructions> tag to create python code for generating the plot asked by the user. A sample of actual data on which the plot is to be generated is given in the <actual_data_sample> tag.
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
"""

##Prompt template to add fewshot examples to the above prompt
query_plot_ex_temp = """<example_{idx}>\n<question>\n{question}\n</question>\n<explanation>\n{reports}\n</explanation>\n<answer>\n{answer}\n</answer>\n</example_{idx}>\n"""


## Prompt template to extract tables related to a text query inorder to determine if a persona is eligible for accessing a table
query_text_tab_tempv3 = """You are an expert in extracting tables from text query. Your job is to extract tables for a question posted by a user.
Follow the instructions in the <instructions> tag to do your job.

Given below are the table names and their descriptions
<table_column_meta>
{schema_meta}
</table_column_meta>

Given below are the meaning of certain tokens present in the questions
<token_interpretation>
{token_intp}
</token_interpretation>

Given below are the mapping of words in questions to tables required in the SQL
<token_table>
1. 'markdown' --> 'markdown'
</token_table>

<output_format>
example1 - ['out1','out2','out3']
example2 - ['out1']
</output_format>

<instructions>
(1).The table names and their descriptions are given in the <table_column_meta> tag. Your job is to extract table names for a question posted by a user 
(2).Carefully analyze the given question to understand the information being requested.
(3).Think through the problem step-by-step, considering the question and the table descriptions. A table can be related to another table
(4).Refer to the information given in the <token_interpretation> tag to understand what are the alternate meaning of tokens used in a question
(5).Refer to the information given in the <token_table> tag to understand the table names required for certain tokens used in the question given by the user. For other tokens, analyze the descriptions provided for tables and columns in the <table_column_meta> tag and identify the required table name and column names required to create SQL query
(6).Your answer should be in the style given in the <output_format> tag
(7).Return only the table names in the <answer> tag and explanation in the <exp> tag
</instructions>
"""

query_text_tab_ex_temp = """<example_{idx}>\n<question>\n{question}\n</question>\n<answer>\n{answer}\n</answer>\n</example_{idx}>\n"""

## Prompt template to rectify SQL query
rectifier_prompt_temp = """You are an expert in rectifying errors in SQL query. A SQL in SQLITE was generated from a question, however, it failed to execute in the database.
Follow the instructions given inside <instructions></instructions> tag.

<question>
{question}
</question>

<sql>
{sql_cmd}
</sql>

<error>
{syntax_error}
</error>

<tab_col>
{tab_col}
</tab_col>

<instructions>
1.Analyze the error given in the <error> tag for the SQL given in the <sql> tag. The question used to generate the SQL is given in the <question>tag
2.Your job is to correct the SQL and rewrite it in SQLITE syntax. Refer to the tables and columns, if required which is given in the <tab_col> tag
3. Return the SQL in the <answer> tag
</instructions>
"""

## Prompt template to rectify python query
rectifier_prompt_py_temp = """You are an expert in rectifying errors in python query to generate plots. A python query to generate plots was generated from a question, however, it failed to execute.
Follow the instructions given in the <instructions> tag.

<question>
{question}
</question>

<python>
{py_cmd}
</python>

<error>
{syntax_error}
</error>

Given below is the sample data which contains all the required columns to create the plot
<sample_data>
{sample}
</sample_data>

<instructions>
1.Analyze the error given in the <error>tag for the python query given in the <python> tag. The question used to generate the python is given in the <question>tag
2.The sample data and columns used to create the plot are given in <sample_data> tag
2.Your job is to correct the python query and rewrite it. You must check if the correct columns from <sample_data> tag are used in the python query. Check for correct syntax also
3. Return the python query in the <answer> tag
</instructions>

IMPORTANT - 
(1). You should import all the required libraries such as matplotlib, pandas inside the python function definition
(2). Just reminding you that your job is to rectify the python function to generate plot. No filters are required on the data

"""

intent_prompt = '''You are an expert data analyst who will perform the following tasks:
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
'''

## Prompt template to create prompt inorder to invoke a LLM to classify a question into categories
QUESTION_CAT ='''You are a data analyst, expert in identifying the category of a business intelligence question.
If you are given a database schema and a user question, you can categorize the question into the following categories:
"data_retrieval_simple" OR "reasoning"

"data_retrieval_simple" questions seek their response as data, either as a single value, a table of records or a chart / plot / figure. 
"data_retrieval_simple" questions usually contain phrases like "what", "who", "how many", "List", "where" etc.

"reasoning" questions seek explanations for an observation. To answer these questions would require first extracting 
relevant data that captures the observation and then looking for a reason to explain the observation based on the data.
The observation is usually stated in the question. If the observation is not stated then the question is asking to first 
extract the data and then reason based on the data. Reasoning questions usually contain phrases like "why", "how do you explain" etc. 

Given the above context,find the category of the following user question:

{user_query}

Please only mention the category as either "data_retrieval_simple" or "reasoning" and return your answer within the <answer></answer> tag

'''
## Prompt template to create prompt inorder to invoke a LLM to modify a complex reasoning question to a simple data_retreival question
question_mod_prompt = '''
You are an expert data analyst who can answer a reasoning question.
To answer a reasoning question, given the question within tags <question></question> and a database schema within tags <Database_Schema></Database_Schema>, you take the following steps:
- First identify the columns in the database schema given within the tags <Database_Schema></Database_Schema> that will help measure the output metrics in the question given within tags <question></question>.
- Next, identify the columns in the database schema given within the tags <Database_Schema></Database_Schema> that are the contributing factors or causes in answering the question within tags <question></question>
- Then, using the columns identified above and the question within <question></question> generate a "data extraction question" that will help extract the relevant data from the database using a corresponding SQL query. The data extraction question should be broad enough to sufficiently make comparisons mentioned in the question.
- Mention all relevant columns from the database schema in the "data extraction question" so that the corresponding SQL query has them in the SELECT statement
- Add the following sentence to each "data extraction question": "Add all the columns and data that you looked at and do not miss any column".

Given the following database schema,

<Database_Schema>
{schema_str}
</Database_Schema>

and the reasoning question

<question>
{user_query}
</question>

generate the "data extraction question" without any additional explanation or commentary within the <answer></answer> tag.

''' 

question_mod_prompt1 = '''
You are an expert data analyst specializing in breaking down complex business questions into specific, data-driven analyses. Your expertise lies in:
- Identifying key metrics and factors needed to answer business questions
- Understanding cause-and-effect relationships in business scenarios
- Breaking down high-level observations into measurable components
- Translating business concerns into data analysis requirements

<context>
The following user question given inside the <question> </question> tag has been classified as COMPLEX_REASONING type. This means:
- The question asks for an explanation of a business observation or trend
- The answer requires analyzing multiple factors or patterns in the data
- The question needs to be modified to focus on extracting relevant data points
</context>

<Database_Schema>
{schema_str}
</Database_Schema>

<question>
{user_query}
</question>

<instructions>
1. Understand the conext given inside the <context></context> tag
2. Given the context and question given inside <question></question> tag, identify the analysis required to answer the business question
3. Basis the data points available inside <schema></schema> tag, determine what metrics or patterns would explain this observation
4. Transform the complex business question given indside <question></question> tag into a single specific data retrieval natural language question
5. Please include all relevant factors including any identifiers or  factors used to filter the data as part of the transofmed question
6. Remember: Return ONLY the trasnformed question without any additional explanation or commentary within the <answer></answer> tag.  
</instructions>
''' 

QUESTION_CAT1 ='''You are an expert in classifying a question into different categories. 
A question is posted by the user and your job is to classify the question into categories as explained in the <question_categories></question_categories> tag.
Follow the instructions inside the <instructions></instructions> tag to do your job.

Analyze the user's question and categorize it into one of two categories based on its complexity. 

### Database Schema:
{schema_str}

<question>
{user_query}
</question>

Given below are the categories to which a question is to be mapped
<question_categories>
1.Category: data_retrieval_simple, Meaning:
   - Straightforward questions that can be directly translated to SQL
   - Clear mapping between question and database schema
   - No complex reasoning or multiple steps required

2.Category: reasoning, Meaning:
   - Questions requiring interpretation or inference
   - Vague or indirect questions needing refinement
   - Questions asking for explanations or patterns
</question_categories>

### Instructions:
<instructions>
(1).Check if the question can be answered using the provided schema
(2).Refer to the categories inside the <question_categories></question_categories> tag to understand the logic to classify a question to a category
(3).Your job is to classify the question inside <question></question> tag into the categories given inside <question_categories></question_categories>
(4).Return your answer inside the <answer></answer> tag
(5).Remember, your answer should only contain one of the two catgeories data_retrieval_simple or reasoning
</instructions>
'''

