#import sys
#sys.path.insert(0, '../')
import os
import sys
import time
import logging
# Get the absolute path to project root dynamically
# One-time path setup at the start of each module
#current_file = os.path.abspath(__file__)
#project_root = os.path.dirname(os.path.dirname(current_file)) #Going 3 levels up to get to project root folder, 
# project_root = '/home/sagemaker-user/data_analyst_bot/da_refactor'
# if project_root not in sys.path:
#     sys.path.insert(0, project_root)
# Now import your module
#from scripts.query_db.classifierv2 import FewShotClfBedrock
#import os
import pandas as pd
import ast
import datetime
import boto3
import json
from scripts.time_tracker import ProcessingTimeTracker
from scripts.query_db.get_tabs import FewShotTabBedrock
from scripts.query_db.classifierv2 import FewShotClfBedrock
#from scripts.query_db.split_query import FewShotSplitterBedrock
from scripts.query_db.modify_user_query import FewShotModifierBedrock

#from scripts.query_db.get_db_data import SQLGenerator
# from scripts.query_db.prompt_generator import PromptGenerator
from scripts.query_db.reasonerv2 import FewShotReasonerBedrock
from scripts.query_db.get_charts import DBPlottingBedrock
from scripts.run_llm_inferencev2 import BedrockTextGenerator
from scripts.utils import extract_data, load_data, extract_py_code
from scripts.utils import verify_file_access

# from scripts.query_db.config import classifier_llm, splitter_llm, sql_llm,text_tabs_llm, plot_llm,rectifier_llm, intent_llm
# from scripts.query_db.config import prompt_type, plot_ex_file, schema_file, table_meta_file, col_meta_file
from scripts.query_db.config import reasoner_llm, table_en_llm
from scripts.query_db.config import words_cat_reason, words_cat_data_ret_simple
from scripts.query_db.config import question_classif, MODEL_CONF, DATA_DIR, META_DIR, INDEX_DIR
from scripts.query_db.config import setup_directories
from scripts.query_db.prompt_config_clv2 import plotting_temp, query_plot_ex_temp, tab_nlq_temp
from scripts.query_db.prompt_config_clv3 import plotting_tempv3, query_plot_ex_temp, tab_nlq_tempv3, intent_prompt, rectifier_prompt_temp, rectifier_prompt_py_temp
from scripts.query_db.postprocessor import run_normalization_process
#from scripts.query_db.db_executor import get_sql_result, get_sql_result2
from scripts.query_db.pgsql_executor import get_sql_result, get_sql_result2
from scripts.query_db.config import SQL_Gen_Lambda
from scripts.query_db.prompt_config_clv3 import question_mod_prompt


# Configure logging
logger = logging.getLogger(__name__)


def invoke_sql_generator_lambda(messages, query, db_config, model_id, embedding_model_id, approach, metadata, session, table_selection, query_tabs=None):
    """
    Invokes an AWS Lambda function to generate SQL queries based on input parameters.
    
    Args:
        messages (list): List of conversation messages providing context for SQL generation.
                        Example: [{"role": "user", "content": "show me sales data"}]
        query (str): The user's natural language query to be converted to SQL.
                    Example: "What were the total sales in 2023?"
        query_tabs (list): List of database tables relevant to the query.
                          Example: ["sales", "products", "customers"]
    
    Returns:
        tuple: A tuple containing two elements:
            - sql_query (str): The generated SQL query if successful, empty string if failed
                              Example: "SELECT SUM(sales_amount) FROM sales WHERE YEAR(sale_date) = 2023"
            - error_msg (str): Error message if any occurred, empty string if successful
                              Example: "Error: Invalid table reference" or ""
    
    Raises:
        No exceptions are raised as they are caught and returned as error messages
    
    Example:
        >>> sql_query, sql_result, error_msg = invoke_sql_generator_lambda(
                messages=[{"role": "user", "content": "show sales for 2023"}],
                query="What were the total sales in 2023?",
                query_tabs=["sales", "products"]
            )
        >>> if error_msg:
        >>>     logger.error("Error: %s", error_msg)
        >>> else:
        >>>     logger.info("Generated SQL: %s", sql_query)
    """
    try:
        lambda_client = boto3.client('lambda')
        
        # Prepare the payload for Lambda function
        payload = {
            "model_id": model_id,
            "embedding_model_id": embedding_model_id,
            "approach": approach,
            "database_type": db_config.get("db_type"),
            "db_conn_conf": {
                "host": db_config.get("host"),
                "port":  db_config.get("port"),
                "database": db_config.get("database"),
                "user": db_config.get("user"),
                "password": db_config.get("password")
            },
            "table_selection": table_selection,
            "metadata":metadata,
            "question": query,
            "messages": messages,
            "session":session
        }
        # payload = {
        #     'messages': messages,
        #     'query': query,
        #     'query_tabs': query_tabs
        # }

        logger.info("QueryBot payload: %s", payload)
        # Invoke the Lambda function
        response = lambda_client.invoke(
            FunctionName= os.environ.get("QUERYBOT_LAMBDA_NAME"),  # Changed from QUERYBOT_LAMBDA_ARN to QUERYBOT_LAMBDA_NAME to match CDK
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        # Parse and process the response
        response_payload = json.loads(response['Payload'].read().decode()) #decode('utf-8')
        logger.debug("response_payload: %s", response_payload)
        # Extract SQL and error message from Lambda response
        if 'statusCode' in response_payload and response_payload['statusCode'] == 200:
            body = json.loads(response_payload['body'])
            return body.get('sql_query', None), body.get('result', None), body.get('error', "")
        else:
            error_msg = response_payload.get('errorMessage', 'Unknown error in SQL generator Lambda')
            return '', None, error_msg  # Return 3 values: sql, result, error
            
    except Exception as e:
        logger.error("Error invoking SQL generator Lambda: %s", e, exc_info=True)
        return '', None, f'Error invoking SQL generator Lambda: {str(e)}'  # Return 3 values: sql, result, error


def get_text_tables(model_id, messages):
    """This function invokes LLM to identify table names elated to a text query . This is to be used 
    for determining persona based access

    Args:
        messages(list): the list of content passed by user and responses from bot
    Returns: The tables and error messages
    """
    model_params = MODEL_CONF[model_id]
    tab_generator = FewShotTabBedrock(model_id)
    #user_message = [{"role": "user", "content":question }]
    tab_gen, error_msg = tab_generator.generate_tables(messages=messages)
    logger.debug('tab_gen before: %s', tab_gen)
    if tab_gen != None:
        tab_gen = ast.literal_eval(tab_gen) if type(tab_gen) == str else tab_gen
    logger.debug('tab_gen after: %s', tab_gen)
    return tab_gen, error_msg

def generate_answer_en(model_id, table_ans, sql, messages):
    """This function invokes LLM to convert a tabular data to natural language

    Args:
        table_ans(dataframe): the tabular data retrieved from database or the output data from 
        python query
        sql(str): the generated SQL from LLM
        messages(list): the list of content passed by user and responses from bot
    Returns: The answer in natural language
    """
    answer_en = ''
    model_params = MODEL_CONF[table_en_llm]
    answer_gen_en = BedrockTextGenerator(model_id, model_params)
    table_ans = table_ans.to_dict(orient='records')
    if 'claude-3' in table_en_llm or "nova" in table_en_llm:
        prompt_en = tab_nlq_tempv3.format(result=table_ans, sql=sql)
        # logger.debug('prompt_en: %s', prompt_en)
        #user_message = [{"role": "user", "content":[{"text": question}]}]
        text_resp, error_msg = answer_gen_en.generate(input_text=messages, prompt=prompt_en)
    elif 'claude-v2' in table_en_llm:
        prompt_en = tab_nlq_temp.format(result=table_ans, question=question)
        text_resp, error_msg = answer_gen_en.generate(prompt=prompt_en)
    logger.debug('text_resp: %s', text_resp)
    if error_msg == '':
        answer_en =  extract_data(text_resp, tag1='<response>',tag2='</response>')
        logger.debug('answer: %s', answer_en)

    return answer_en, error_msg

def get_question_categories(question):
    """This function is used to classify a question into categories using heuristics rules

    Args:
        question (str): text query
    Returns: The category of the question
    """
    question_cat = ''
    question_act = question
    question_lcase = question_act.lower()
    question_toks = question_lcase.split()
    for tok in words_cat_reason:
        if tok in question_toks:
            question_cat = 'reasoning'
            return question_cat
    if question_cat == '':
        for tok in words_cat_data_ret_simple:
            if tok in question_toks:
                question_cat = 'data_retrieval_simple'
                return question_cat
        if question_cat == '':
            return 'data_retrieval_simple'

# query_tabs is not needed
# /home/sagemaker-user/data_analyst_bot/da_refactor/scripts/query_db/pgsql_executor.py
def generate_answers_db(query, query_type, messages, schema_extractor, schema_str, db_config, chat_model_id, sql_model_id, embedding_model_id, approach, metadata, session, table_selection, q_mod_prompt = None, query_tabs=None, iteration_id=None, time_tracker=None):
    """Section to invoke modules to generate answers for a usecase involving database

    Args:
        query (str): text query
        query_tabs (list): list of relevant tables for a question
        messages(list): the list of content passed by user and responses from bot
        schema_extractor : An instance of the DatabaseSchemaExtractor class
        schema_str (str): the schema information of the database in a string format
    Returns: The answer in natural language, the generated SQL and error messages
    """
    answer_gen = ''
    error_msg = ''
    sql_gen = ''
    prompt = ''
    cat_gen = ''
    split_gen = ''
    suggestion = ''
    table_ans = pd.DataFrame()  # Initialize as empty DataFrame instead of string
    df = None
    replacement_message = ''
    if q_mod_prompt is None:
        q_mod_prompt = question_mod_prompt

    # model_id = "anthropic.claude-3-sonnet-20240229-v1:0"     
    # anthropic.claude-3-5-sonnet-20240620-v1:0
    # anthropic.claude-3-sonnet-20240229-v1:0
    try:
        # Question Classification
        if query_type == "aggregation":
            # SQL Generation
            time_tracker.start_process(iteration_id, "aggregation - sql_generation")
            st = time.time()
            try:
                sql_gen, sql_result, error_msg = invoke_sql_generator_lambda(messages, query, db_config, sql_model_id, embedding_model_id, approach, metadata, session, table_selection, query_tabs)
            except ValueError as ve:
                logger.error("Unpacking error in invoke_sql_generator_lambda: %s", ve)
                raise
            end = time.time()
            logger.info(f"End to end invokation in invoke_sql_generator_lambda:{end-st}")
            logger.debug("sql_gen: %s", sql_gen)
            
            time_tracker.end_process(iteration_id)


            if error_msg == '':
                if db_config.get("db_type") == 's3':
                    try: 
                        table_ans = pd.DataFrame([sql_result]) if isinstance(sql_result, dict) else pd.DataFrame(sql_result)
                        error_msg = ''
                    except Exception as e:
                        logger.error(f"Error converting SQL result {sql_result} to DataFrame: {str(e)}")
                        table_ans = pd.DataFrame()
                        error_msg = f"Error converting SQL result to DataFrame: {str(e)}"
                else:
                    # SQL Execution
                    time_tracker.start_process(iteration_id, "data_retreival_simple - sql_execution")

                    gen_text = get_sql_result(sql_gen, schema_extractor) #execute SQL - pgsql_executor module
                    logger.debug('gen_text: %s', gen_text)
                    table_ans = gen_text[0]
                    error_msg = gen_text[1]
                    
                    time_tracker.end_process(iteration_id)

                    # SQL Rectification (if needed)
                    iter_no = 1
                    logger.debug(f"Iteration Number: {iter_no}, Error message in execution: {error_msg} ")
                    
                    time_tracker.start_process(iteration_id, "data_retrival_simple - sql_re-execution")
                    
                    while 'Execution failed' in error_msg and iter_no < 4:
                        #sql_gen = rectify_SQL(query, sql_gen, error_msg) # No rectification is needed
                        gen_text = get_sql_result(sql_gen, schema_extractor) #execute SQL - pgsql_executor module
                        table_ans = gen_text[0]
                        error_msg = gen_text[1]
                        logger.debug(f"Iteration Number: {iter_no}, Error message in execution: {error_msg} ")
                        iter_no += 1
                    
                    time_tracker.end_process(iteration_id)
                
                if error_msg != '':
                    answer_gen = ''
                else:
                    time_tracker.start_process(iteration_id, "data_retreival_simple - Normalization")
                    try:
                        sql_gen, table_ans, error_msg, suggestion, replacement_message = run_normalization_process(sql_gen, table_ans, schema_extractor) # No Normalization
                    except ValueError as ve:
                        logger.error("Unpacking error in run_normalization_process: %s", ve)
                        raise
                    time_tracker.end_process(iteration_id)

                    time_tracker.start_process(iteration_id, "data_retreival_simple - Explanation generation")
                    if error_msg != '':
                       answer_gen = ''                    
                    elif error_msg == '' and table_ans.shape[0] == 0:
                        # answer_gen = ''
                        answer_gen = suggestion
                    elif error_msg == '' and table_ans.shape[0] > 0:
                        logger.debug("message: %s", messages)
                        answer_gen, error_msg = generate_answer_en(chat_model_id, table_ans, sql_gen, messages)
                    
                    time_tracker.end_process(iteration_id)
                #logger.debug('error_msg in orc', error_msg)
        elif query_type == "reasoning":
            # Subquestion Generation

            time_tracker.start_process(iteration_id, "Reasoning - Sub question generation")

            modques_generator = FewShotModifierBedrock(chat_model_id)
            logger.debug("Invoking Question Modifier")
            # logger.debug("Q_Mod_Prompt in generate answers db:\n", q_mod_prompt)
            try:
                split_gen, error_msg, mod_ques_prompt = modques_generator.generate_subquery(messages, query, cat_gen, schema_str,q_mod_prompt)
            except ValueError as ve:
                logger.error("Unpacking error in generate_subquery: %s", ve)
                raise
            prompt = mod_ques_prompt

            time_tracker.end_process(iteration_id)


            if error_msg == '':
                # SQL Generation
                time_tracker.start_process(iteration_id, "Reasoning -  SQL generation")

                split_gen_add = 'While generating the SQL for this question, if any attributes are used as filtering criteria (in WHERE, HAVING, or similar conditions), always include these same attributes in the list of columns to be retrieved in SQL select statement, even if they are only used for filtering or as any other identifier'
                mod_ques = split_gen + '\n' + split_gen_add
                logger.debug('split_gen: %s', split_gen)
                user_msg = [{"role": "user", "content":[{"text": split_gen}]}]
                # Passing mod_ques after concatenating with split_gen
                logger.debug("Model ID for SQL Invocation : %s", sql_model_id)
                sql_gen, sql_result, error_msg = invoke_sql_generator_lambda(messages, mod_ques, db_config, sql_model_id, embedding_model_id, approach, metadata, session, query_tabs)
                
                time_tracker.end_process(iteration_id)
                
                if error_msg == '':
                    if db_config.get("db_type") == 's3':
                        try: 
                            table_ans = pd.DataFrame([sql_result]) if isinstance(sql_result, dict) else pd.DataFrame(sql_result)
                            error_msg = ''
                        except Exception as e:
                            logger.error(f"Error converting SQL result {sql_result} to DataFrame: {str(e)}")
                            table_ans = pd.DataFrame()
                            error_msg = f"Error converting SQL result to DataFrame: {str(e)}"
                    else:
                        # SQL Execution
                        time_tracker.start_process(iteration_id, "Reasoning - sql_execution")
        
                        gen_text = get_sql_result(sql_gen, schema_extractor) #execute SQL - pgsql_executor module
                        table_ans = gen_text[0]
                        error_msg = gen_text[1]

                        time_tracker.end_process(iteration_id)

                    iter_no = 1
                    logger.debug("table_ans: %s", table_ans)

                    time_tracker.start_process(iteration_id, "Reasoning sql_re-execution")

                    while 'Execution failed' in error_msg and iter_no < 4:
                        #sql_gen = rectify_SQL(query, sql_gen, error_msg)
                        gen_text = get_sql_result(sql_gen, schema_extractor) #execute SQL - Get code from SQLGen Asset
                        table_ans = gen_text[0]
                        error_msg = gen_text[1]
                        iter_no += 1

                    time_tracker.end_process(iteration_id)

                    if error_msg != '':
                        answer_gen = ''
                    else:
                        time_tracker.start_process(iteration_id, "Reasoning - result_ explanation generation")

                        reason_generator = FewShotReasonerBedrock(reasoner_llm)
                        logger.debug("Trying to generate Reasoning")
                        try:
                            answer_gen, error_msg = reason_generator.generate_reasoning(messages, query, table_ans)
                        except ValueError as ve:
                            logger.error("Unpacking error in generate_reasoning: %s", ve)
                            raise

                        time_tracker.end_process(iteration_id)

    except Exception as e:
        error_type = type(e).__name__
        error_message = str(e)
        logger.error(f"Error in generate_answers - Type: {error_type}, Message: {error_message}")
        if time_tracker.current_process:
            time_tracker.end_process(iteration_id)
    return answer_gen, sql_gen, error_msg, cat_gen, split_gen, prompt, table_ans, suggestion, replacement_message


def rectify_python(model_id, question, python, sample_data, error):
    """Section to rectify syntax errors in python query by invoking LLMs. The python query is used to generate plots

    Args:
        question (str): text query
        python (str): python query
        sample_data(DataFrame): the sample data on which the plot to be generated
        error(str): error message upon execution of SQL
    Returns: The rectified python query
    """
    python = ''
    logger.debug('Rectifying python')
    model_params = MODEL_CONF[model_id]
    prompt = rectifier_prompt_py_temp.format(question=question, py_cmd=python, syntax_error=error, sample=sample_data)
    generator = BedrockTextGenerator(model_id, model_params)
    #messages = [{"role": "user", "content":prompt }]
    messages = [{"role": "user", "content":[{"text": prompt}]}]
    text_resp, error_msg = generator.generate(prompt='Rectify the python query', input_text=messages)
    if error_msg == '':
        python = extract_py_code(text_resp)
    return python, error_msg


def generate_plots(query, messages, schema_extractor, db_config, chat_model_id, sql_model_id, embedding_model_id, approach, metadata, session, query_tabs=None):
    # model_id = "anthropic.claude-3-sonnet-20240229-v1:0"    
    try:
        # Ensure directories exist at the start
        setup_directories()
        
        # Verify DATA_DIR is properly set up
        logger.debug("Verifying DATA_DIR setup...")
        verify_file_access(DATA_DIR)
        
        plot_gen = ''
        python_query = ''

        logger.debug("Inside generate plots")
        sql_gen,  sql_result, error_msg = invoke_sql_generator_lambda(messages, query, db_config, sql_model_id, embedding_model_id, approach, metadata, session, query_tabs)
        logger.debug('sql gen in plot: %s', sql_gen)

        if db_config.get("db_type") == 's3':
            try: 
                table_ans = pd.DataFrame([sql_result]) if isinstance(sql_result, dict) else pd.DataFrame(sql_result)
                error_msg = ''
            except Exception as e:
                logger.error(f"Error converting SQL result {sql_result} to DataFrame: {str(e)}")
                table_ans = pd.DataFrame()
                error_msg = f"Error converting SQL result to DataFrame: {str(e)}"
        else:
            logger.debug("Before get_sql_result")
            gen_text = get_sql_result(sql_gen, schema_extractor)
            logger.debug("After get_sql_result")
            logger.debug("gen_text: %s", gen_text)
        
            table_ans = gen_text[0]
            error_msg = gen_text[1]    
            logger.debug(f"table_ans shape: {table_ans.shape if hasattr(table_ans, 'shape') else 'No shape'}")
            logger.debug(f"error_msg: {error_msg}")

            iter_no = 1
            while 'Execution failed' in error_msg and iter_no < 4:
                logger.debug(f"Retry attempt {iter_no}")
                gen_text = get_sql_result(sql_gen, schema_extractor)
                table_ans = gen_text[0]
                error_msg = gen_text[1]
                iter_no += 1

        if error_msg == '':
            logger.debug("No error, proceeding with plot generation")
            
            # Create the full path for the CSV file
            csv_path = os.path.join(DATA_DIR, 'sql_db_out.csv')
            logger.debug(f"Attempting to save CSV to: {csv_path}")
            
            # Save the CSV file
            table_ans.to_csv(csv_path, index=None)
            
            # Verify the CSV file was created successfully
            if not verify_file_access(csv_path):
                raise FileNotFoundError(f"Failed to create or access CSV file at {csv_path}")
            
            plot_generator = DBPlottingBedrock(chat_model_id)
            python_query, error_msg = plot_generator.generate_python(query, table_ans)
            logger.debug(f"After generate_python - error_msg: {error_msg}")
            
            if error_msg == '':
                logger.debug(f"Python query to be executed:\n{python_query}")
                plot_gen, error_msg = plot_generator.generate_plot(python_query)
                logger.debug(f"After generate_plot - Type of plot_out: {type(plot_gen)}")
                logger.debug(f"Type of table_ans: {type(table_ans)}")
                logger.debug(f"After generate_plot - error_msg: {error_msg}")
               

                if error_msg == '':
                    # Verify any output files created during plot generation
                    plot_output_path = os.path.join(DATA_DIR, 'plot_output.png')  # adjust filename as needed
                    #plot_gen.savefig(plot_output_path)
                    #logger.debug("Attempted to save plot to %s", plot_output_path)
                    if plot_gen and verify_file_access(plot_output_path):
                       logger.debug("Plot file successfully generated and verified")
                    return plot_gen, python_query, table_ans, error_msg
                    
                elif error_msg != '':
                    logger.debug("System encountered an exception. Re-running the plot generator")
                    python_query, error_msg = plot_generator.generate_python(query, table_ans)
                    logger.debug(f"After re_generate_python - error_msg: {error_msg}")
                    if error_msg == '':
                        plot_gen, error_msg = plot_generator.generate_plot(python_query)
                        logger.debug(f"After re_generate_plot - Type of plot_out: {type(plot_gen)}")
                        logger.debug(f"Type of table_ans: {type(table_ans)}")
                        logger.debug(f"After re_generate_plot - error_msg: {error_msg}")


                        if error_msg == '':
                            # Verify plot file after retry
                            plot_output_path = os.path.join(DATA_DIR, 'plot_output.png')  # adjust filename as needed
                            if verify_file_access(plot_output_path):
                                logger.debug("Plot file successfully generated after retry")
                            return plot_gen, python_query, table_ans, error_msg
                        else:
                            logger.debug('Running the python rectification module to correct the exception - %s', error_msg)
                            sample_data = table_ans.head(3)
                            python_query, error_msg = rectify_python(sql_model_id, query, python_query, sample_data, error_msg)
                            if error_msg == '':
                                plot_gen, error_msg = plot_generator.generate_plot(python_query)
                                # Final verification of plot file
                                plot_output_path = os.path.join(DATA_DIR, 'plot_output.png')  # adjust filename as needed
                                if error_msg == '' and verify_file_access(plot_output_path):
                                    logger.debug("Plot file successfully generated after rectification")
                            return plot_gen, python_query, table_ans, error_msg    
        else:
            error_msg = f'Data cannot be extracted for plotting due to - {error_msg}'
            logger.debug(error_msg)
            return plot_gen, python_query, table_ans, error_msg
            
    except Exception as e:
        logger.error(f"Exception in generate_plots: {str(e)}")
        logger.debug(f"Current working directory: {os.getcwd()}")
        import traceback
        logger.debug(traceback.format_exc())
        return None, None, None, f"Plot generation failed: {str(e)}"

# Changes : Added default argument query_prompt to question_intent() function
def question_intent(model_id, messages, query_prompt = intent_prompt, schema_str = "", guardrail=False):
    """This function invokes LLM to identify the nature of a question -  greetings or a question requiring SQL generation

    Args:
        question (str): the current question
    Returns: Yes or No corresponding to whether the question requires code to be generated or related to casual conversation
    """
    # messages = []
    error_msg = ''
    final_response = ''
    answer = ''
    reformulated_question = ''
    model_params = MODEL_CONF[model_id]
    # messages = [{"role": "user", "content":[{"text": question}]}]
    #query_prompt = QUESTION_INTENT
    generator = BedrockTextGenerator(model_id, model_params)
    answer, error_msg = generator.generate(prompt=query_prompt.format(schema_str=schema_str), input_text=messages, apply_guardrail=True)
    if error_msg == '':
        logger.debug('answer intent: %s', answer)
        if '<answer>' in answer:
            final_response = extract_data(answer, tag1='<answer>', tag2='</answer>')
            reformulated_question = extract_data(answer, tag1='<question>', tag2='</question>')
        else:
            final_response = answer
    logger.debug(f"Question intent result: \n - AI answer: {answer} \n - Final answer: {final_response} \n - Reformulated question: {reformulated_question}")
    return query_prompt, answer, final_response, reformulated_question, error_msg