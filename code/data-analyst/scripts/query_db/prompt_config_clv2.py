"""
This file contains the different prompt templates for claude version <3 to create prompt for different stages in the workflow
"""
## Prompt template to create prompt inorder to invoke a LLM to classify a question into categories
query_clf_temp = '''\n\nHuman: You are an expert in classifying a question into different categories. 
A question is given in the <question></question> tag and your job is to classify the question into categories as explained in the <question_categories></question_categories> tag.
Follow the instructions inside the <instructions></instructions> tag to do your job.

Given below are the categories to which a question is to be mapped
<question_categories>
1.Category: reasoning, Meaning: The intent of the questions in this category is about why certain things happen. Here  analysis of different factors are required, cause and effect analysis etc
2.Category: data_retrieval_simple, Meaning: The intent of the questions in this category is about only retrieving the data without any mathematical computations
2.Category: data_retrieval_complex, Meaning: The intent of the questions in this category is about  retrieving the data and also computing some indicators such as growth rate or proportions or correlations etc
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

<question>
{question}
</question>
\n\nAssistant:'''

## Prompt template to add fewshot examples to the above prompt
fshot_temp = "<example_{idx}>\n<question>\n{question}\n</question>\n<answer>\n{answer}\n</answer>\n</example_{idx}>\n"


QUESTION_CATv2 ='''\n\nHuman: You are a data analyst, expert in identifying the category of a business intelligence question.
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

\n\nAssistant:
'''


## Prompt template to create prompt inorder to invoke a LLM to break a question into subqueries
query_split_temp = '''\n\nHuman:You are an expert in breaking a main question into sub questions and associating the subquestions to a category. Given below inside <question_split_criteria></question_split_criteria> are some criteria to split the main question and also the categoires to which a subquestion to be assigned. Follow the instructions inside the <instructions></instructions> tag to do your job.

The question given inside <question></question> tag is a {qtype} based question.

Given below is some information on what factors can impact a metric. Use these factors only for reasoning questions
<relevant_factors>
{metric_vars}
</relevant_factors>

<question_split_criteria>
{criteria}
</question_split_criteria>

Given below are some examples which depict how to split a main question into subquestions
<examples>
{ex}
</examples>

<instructions>
1. Strictly understand the rules if available inside <question_split_criteria></question_split_criteria> tag to split a main question given inside <question></question> tag to multiple sub questions
2. Map the subquestions that you generate to a category defined inside the <question_split_criteria></question_split_criteria> tag 
3. If the question is a reasoning based question, then refer to the information inside <relevant_factors></relevant_factors> to understand the factors which can impact a metric
4.Follow the examples inside the <examples></examples> tag and understand how a main question is split into multiple sub questions and how they are mapped to a category. You must generalize this knowledge to new main questions
5. The sub questions that you create should only ask for the data that is to be retrieved, don't explain the reason
6. Return the multiple sub questions in different tags. For example, if the question is split into two sub questions, then the first sub question along with its category to be returned inside the <subquestion1></subquestion1> tag, and the second sub question along with its category to be returned inside the <subquestion2></subquestion2> tag
</instructions>

<question>
{question}
</question>
\n\nAssistant:'''

## Prompt template to add feshot examples to the above prompt
split_fshot_temp = "\n<example_{idx}>\n{question}\n<explanation>\n{expl}\n</explanation>\n{qparts}\n</example_{idx}>\n"

qpart_temp = "<subquestion{idx}>\n{qpart}\n</subquestion{idx}>\n"


## Prompt template to create prompt inorder to invoke a LLM to generate SQL query 
query_sql_temp = '''\n\nHuman: You are an expert in generating SQL query from text query. Your job is to generate SQL query for a question given inside the <question></question> tag
Follow the instructions inside the <instructions></instructions> tag to do your job.

Given below are the tables, corresponding columns
<table_column_meta>
{schema_meta}
</table_column_meta>

Given below are the various joins between the tables
<table_joins>
sales.Store = markdown.Store
sales.Store = holiday.Store
sales.Store = inflation.Store
sales.Store = inflation.Store
sales.Store = inflation.Store
sales.Store = inflation.Store
sales.Store = inflation.Store
</table_joins>

Given below are the different tables and columns and the type of information each stores
<table_glossary>
{glossary}
</table_glossary>

Given below are the meaning of certain tokens present in the questions
<token_interpretation>
{token_intp}
</token_interpretation>

Given below are the examples which show how a SQL is constructed from a question
<examples>
{ex}
</examples>

<instructions>
(1).Your job is to create a SQL query in SQLITE which can retrieve the data to do analysis. Follow the examples inside <examples></examples> to learn
(2).Refer to the information inside the <table_column_meta></table_column_meta> tag to get the relevant tables and their columns required to create a SQL
(3).Refer to the information inside <token_interpretation></token_interpretation> to understand the meaning of a word in a question
(4).Diligently follow all the steps from (1) to (5) given above and think step by step to create SQL for the question posted by the user
(5).Return the SQL inside the <answer></answer> tag and your step by step reasoning to construct SQL in the <explanation></explanation> tag
</instructions>

<question>
{question}
</question> 
\n\nAssistant:'''

## Prompt template to add fewshot examples to the above prompt
query_sql_ex_temp = "<example_{idx}>\n<question>\n{question}\n</question>\n<answer>\n{answer}\n</answer>\n</example_{idx}>\n"

## Prompt template to create fewshot prompt inorder to invoke a LLM to generate SQL query 
query_sql_zshot_temp = '''\n\nHuman: You are an expert in generating SQL query from text query. Your job is to generate SQL query in SQLITE for a question given inside the <question></question> tag
Follow the instructions inside the <instructions></instructions> tag to do your job.

Given below are the tables, corresponding columns
<table_column_meta>
{schema_meta}
</table_column_meta>

Given below are the various joins between the tables
<table_joins>
</table_joins>

Given below are the meaning of certain tokens present in the questions
<token_interpretation>
{token_intp}
</token_interpretation>

<instructions>
(1).Your job is to create a SQL query in SQLITE which can retrieve the data to do analysis
(2).Refer to the information inside the <table_column_meta></table_column_meta> tag to get the relevant tables and their columns required to create a SQL
(3).Refer to the information inside <token_interpretation></token_interpretation> to understand the meaning of a word in a question
(4).Diligently follow all the steps from (1) to (5) given above and think step by step to create SQL for the question posted by the user
(5).Return the SQL inside the <answer></answer> tag and your step by step reasoning to construct SQL in the <explanation></explanation> tag
</instructions>

<question>
{question}
</question> 
\n\nAssistant:'''



## Prompt template to create prompt to invoke a LLM to convert results in structured table to natural language 
tab_nlq_temp = '''\n\nHuman:The user has asked a question given below:
<question>
{question}
</question>

The following is the result table of the query:
<result>
{result}
</result>

Your task is to briefly interpret and summarize the result table in a human-readable format.
Please try not to use terms like table, row, column, etc. in your output as it is intended for non-technical users.
Put your answer in <response></response> tag.
\n\nAssistant:'''


#################Reasoning based##############################

## Prompt template to create prompt to invoke LLM to generate deductive reasoning
query_reasoning_temp = '''\n\nHuman: You are a smart mathematical analyst and a reasoner. You have to generate a reasoning based answer for the question given inside <question></question> tag by performing deductive reasoning on the data given inside <data></data> tag. Strictly follow the instructions given inside the <instructions></instructions> tag to do your job.

Follow the instructions inside the <instructions></instructions> tag to do your job.

Given below are the meaning of certain tokens present in the questions
<token_interpretation>
{token_intp}
</token_interpretation>

Given below is information on what factors can impact a metric. Use these factors only for reasoning questions
<relevant_factors>
{metric_vars}
</relevant_factors>

Given below are the details on how you must structure your answer. Follow the guidelines on what sections you must include in your answer.
<answer_style>
{style}
</answer_style>

Given below are some examples which show how to generate a python function definition to a text query
<examples>
{ex}
</examples>

You are already good in doing arithmetic operations, but you must refer to the information given below to augment your knowledge 
<arithmetic_computations>
{arith_ops}
</arithmetic_computations>

<instructions>
(1).Your job is to generate answer to the question posted by the user using the data given inside <data></data> tag. 
(2).Carefully read the question, analyze the data inside <data></data> tag properly and generate answers
(3).Use your knowledge in doing arithmetic operations and also refer to the examples inside <arithmetic_computations></arithmetic_computations> to learn to do numerical analysis
(4).Strictly refer to the information inside the <token_interpretation></token_interpretation> tag to understand the meaning of different words in a question
(5).Strictly refer to the metrics and corresponding factors inside <relevant_factors></relevant_factors> tag to identify the metric and the corresponding factors required to answer a question
(6).Strictly follow the rules inside the <answer_style></answer_style> tag to understand how you should structure your answer and what all sections you must include yin your answer
(7).Follow the examples given inside the <examples></examples> for guidance. Following these examples, understand how to do construct a reasoning based answer
(8)If the question is missing out on some details, Refer to the previous questions in the conversation to expand the question
(9).As described in the <answer_style></answer_style> tag, strictly put your calculations inside the <calculations></calculations>, your factor analysis inside the  <factor_contribution></factor_contribution> tag
</instructions>

Given below is the data on which the answers to the question is to be generated
<data>
{data}
</data>

Given below is the question
<question>
{question}
</question>
\n\nAssistant:'''


#################Plotting##############################

## Prompt template to create prompt to invoke LLM to generate python query to plot
plotting_temp = '''\n\nHuman: You are an expert python coder. You are good at using python code to load the relevant data, perform transformations on the data and create different types of plots. Follow the instructions inside the <instructions></instructions> tag to create python code for the question given inside <question></question> tag

Given below is the path to the data you should load
<data_path>
{file_path}
</data_path>

Given below are the columns present in the above data. You must use these columns to plot
<data_columns>
{cols}
</data_columns>

Some examples are given inside the <example></example> tag on how to interpret the data and create plots.
<examples>
{ex}
</examples>

Some rules to be followed while plotting are given below:
<plotting_rules>
1.In the x axis, the x tick values should be rotated by 90 degrees
2.while plotting grouped barcharts, the barwidth should be added to the numeric number
</plotting_rules>

<instructions>
(1).Your job is to understand the question given inside <question></question> tag, create a python function and load the data from the path given inside <data_path></data_path> tag and create plots
(2).Mandatorily only use the necessary columns given inside the <data_columns></data_columns> tag based on the question asked to create the necessary plots. Donot deviate from selecting columns from this list
(3).Refer to the examples inside the <examples></examples> tag if available for guidance
(4).Follow the plotting rules given inside the <plotting_rules></plotting_rules> tag
(5).The python function that you create should return the figure
(6).The plots should be in the same figure plot and use different color codes to represent different entities
(7).After the function definition, assign the relevant data filenames to appropriate variables
(8).Call the python function after the end of the function definition with the filename variables 
(9).Collect the returned value from the function call in a variable named "plot_out". Donot deviate from this
(10).If the data is not available, then donot plot and return empty figure
(11).Return your the python function definition and function call inside the <answer></answer> tag and your step by step reasoning to construct python defintion in the <explanation></explanation> tag
</instructions>

Given below is the question
<question>
{question}
</question>
\n\nAssistant:'''

##Prompt template to add fewshot examples to the above prompt
query_plot_ex_temp = "<example_{idx}>\n<question>\n{question}\n</question>\n<ex_data>\n{reports}\n</ex_data>\n<answer>\n{answer}\n</answer>\n</example_{idx}>\n"


## Prompt template to extract tables related to a text query inorder to determine if a persona is eligible for accessing a table
query_text_tab_temp = '''\n\nHuman: You are an expert in extracting tables from text query. Your job is to extract tables for a question given inside <question></question> tag
Follow the instructions inside the <instructions></instructions> tag to do your job.

Given below are the tables, corresponding columns
<table_column_meta>
{schema_meta}
</table_column_meta>


Given below are the examples which show how tables are extracted for a question
<examples>
{ex}
</examples>

<instructions>
(1). your job is to extract tables for a question posted by a user using the information given inside <table_column_meta></table_column_meta>
(2).For guidance, refer to the examples inside the <examples></examples> tag on how tables are extracted from a sample question
(3).Return the extracted tables inside the <answer></answer> tag
</instructions>

Given below is the question
<question>
{question}
</question>
\n\nAssistant:'''


query_text_tab_ex_temp = "<example_{idx}>\n<question>\n{question}\n</question>\n<answer>\n{answer}\n</answer>\n</example_{idx}>\n"