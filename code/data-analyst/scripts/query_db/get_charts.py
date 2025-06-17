import os
import sys
# project_root = '/home/sagemaker-user/data_analyst_bot/da_refactor'
# if project_root not in sys.path:
#     sys.path.insert(0, project_root)

import re
import pandas as pd
# import seaborn as sns
import datetime
import types
#import pickle
from scripts.query_db.config import DATA_DIR, MODEL_CONF, plot_ex_file, criteria, token_interpretation, filter_rules, PLOT_FILE
from scripts.query_db.prompt_config_clv2 import plotting_temp, query_plot_ex_temp
from scripts.query_db.prompt_config_clv3 import plotting_tempv3, query_plot_ex_temp
from scripts.utils import load_data, extract_py_code, extract_data, log_error
from scripts.run_llm_inferencev2 import BedrockTextGenerator


"""The given prompt template below is used to create a prompt for extracting the relevant entity and their values from the query
"""

class DBPlottingBedrock():
    
    _allowed_model_ids = MODEL_CONF.keys()
    
    def __init__(self, modelid: str):
        if modelid not in self._allowed_model_ids:
            raise ValueError(f'Error: model_id should be chosen from {self._allowed_model_ids}')
        self.modelid = modelid
        self.model_params = MODEL_CONF[modelid]
        self.prompt_type = 'fewshot'

    def create_fshot_prompt(self, question, answer):
        """This function is to be used to generate fewshot prompt

        Args:
        question (str): text query
        answer (DataFrame): the results retrieved from database
        
        Returns: The fewshot prompt
        """
        file_path = os.path.join(DATA_DIR,'sql_db_out.csv')
        df = answer.head(4)
        sample_data = df
        cols = answer.columns.tolist()
        df_prompt_ex = load_data(DATA_DIR, plot_ex_file)
        ex_nlq_list = df_prompt_ex['nlq'].values.tolist()
        print('no of examples', len(ex_nlq_list))
        examples = ''''''
        for i, nlq in enumerate(ex_nlq_list):
            ex_report = df_prompt_ex['explanation'].values.tolist()[i]
            ex_python_code = df_prompt_ex['answer'].values.tolist()[i]
            fshot_data = query_plot_ex_temp.format(idx=i, question=nlq, reports=ex_report,
                                                   answer=ex_python_code)
            examples += fshot_data
        if 'claude-3' in self.modelid or 'nova' in self.modelid or 'llama' in self.modelid:
            fshot_prompt = plotting_tempv3.format(file_path=file_path, sample=sample_data, ex=examples)
            print('fshot_prompt',fshot_prompt)
        elif 'claude-v2' in self.modelid:
            fshot_prompt = plotting_temp.format(cols=cols, ex=None, question=question)
        return fshot_prompt

    def generate_python(self, question, answer):
        """Section to invoke modules to generate fewshot prompt and generate python query to 
        generate charts

        Args:
        question (str): text query
        answer (DataFrame): the results retrieved from database
        
        Returns: the generated python query
        """
        py_gen = ''
        messages = [{"role": "user", "content":[{"text": question + '.The data is filtered,donot filter the data'}]}]
        prompt = self.create_fshot_prompt(question, answer)
        plot_generator = BedrockTextGenerator(self.modelid, self.model_params)
        text_resp, error_msg = plot_generator.generate(input_text=messages, prompt=prompt)
        if error_msg == '':
            py_gen = extract_py_code(text_resp)
        return py_gen, error_msg

    def generate_plot(self, py_gen):
        """Section to execute the python query and generate charts

        Args:
        py_gen (str): generated python query
        
        Returns: the plot object and error messages, if any
        """
        plot_out = ''
        error_msg = ''
        print('py_gen:', py_gen)
        
        try:
            # First, ensure we have a valid Python string
            if not isinstance(py_gen, str):
                raise ValueError("Input must be a string containing Python code")

            # Clean and validate the Python code
            py_gen = py_gen.strip()
            if not py_gen:
                raise ValueError("Empty Python code received")

            # Create a namespace for execution
            namespace = {}
            namespace.update(globals())

            # Add necessary imports to namespace
            exec("import matplotlib.pyplot as plt", namespace)
            exec("import pandas as pd", namespace)
            exec("import numpy as np", namespace)

            # Compile and execute the code
            try:
                exec(py_gen, namespace)
            except Exception as e:
                raise Exception(f"Error executing Python code: {str(e)}")

            # Look for the plot function in the namespace
            plot_func = None
            for name, obj in namespace.items():
                if callable(obj) and name.startswith('plot_'):
                    plot_func = obj
                    break

            if plot_func is None:
                raise ValueError("No plotting function found in the generated code")

            # Assign data path
            data_path = os.path.join(DATA_DIR, PLOT_FILE)
            print(f"Data path: {data_path}")

            # Call the plotting function
            plot_out = plot_func(data_path)
            print(f"Type of plot_out: {type(plot_out)}")

            # Handle the plot output
            if hasattr(plot_out, 'savefig'):  # Check if it's a matplotlib figure
                plot_output_path = os.path.join(DATA_DIR, 'plot_output.png')
                print("Plot_output_path for saving Plot:", plot_output_path)
                plot_out.savefig(plot_output_path)
                print(f"Successfully saved plot to {plot_output_path}")
            else:
                raise ValueError("Generated plot is not a valid matplotlib figure")

        except Exception as e:
            error_msg = str(e)
            print(f"Error in generate_plot: {error_msg}")
            log_error('DBPlottingBedrock', error_msg)
            
        return plot_out, error_msg


'''    
    def generate_plot(self, py_gen):
        """Section to execute the python query and generate charts

        Args:
        py_gen (str): generated python query
        
        Returns: the plot object and error messages, if any
        """
        plot_out = ''
        error_msg = ''
        print('py_gen', py_gen)
        try:
            error = None
            # loc = {}
            # exec(py_gen, loc)
            # plot_ans = loc['plot_out']
            
            # Compile the code string into a code object
            code_obj = compile(py_gen, "<string>", "exec")

            # Get the function code object from the compiled code
            func_code = ''
            code_objs = code_obj.co_consts
            for obj in code_objs:
                if 'code object' in str(obj):
                    func_code = obj

            # Create a new function object from the function code
            func_name = func_code.co_name
            func_closure = func_code.co_freevars
            func = types.FunctionType(func_code, globals(), func_name, tuple(), func_closure)

            # Assign data path
            data_path = os.path.join(DATA_DIR, PLOT_FILE)
            print(f"Data path: {data_path}")

            # Call the function
            plot_out = func(data_path)
            print(f"Type of plot_out: {type(plot_out)}")

            # if isinstance(plot_out, plt.Figure):
            # if isinstance(plot_out, matplotlib.figure.figure):    
            # Check type using string representation
            if str(type(plot_out)) == "<class 'matplotlib.figure.Figure'>":
                plot_output_path = os.path.join(DATA_DIR, 'plot_output.png')
                print("Plot_output_path for saving Plot :",plot_output_path)
                plot_out.savefig(plot_output_path)
                print(f"Attempted to save plot to {plot_output_path}")    


        except Exception as e:
            error_msg = str(e)
            print(f"Error in generate_plot: {error_msg}")
            log_error('DBPlottingBedrock', error_msg)
        return plot_out, error_msg
'''
