import os
import sys
import json
import pandas as pd
import datetime
import logging
import json
from glob import glob
import boto3
from scripts.query_db.config import DATA_DIR, is_lambda_environment


def get_deployment_package_path():
    """
    Function to get the path to deployment package files in Lambda
    """
    if is_lambda_environment():
        # Lambda deployment package is extracted to /var/task
        return '/var/task'
    else:
        # Local development path
        return os.path.join(os.getcwd(), 'data_analyst_ra_test')

def load_data(DATA_DIR, file):
    """
    Function to load the data from a path, handling both temporary and deployment package files

    Args:
    DATA_DIR(str): The path where the data resides
    file(str): The filename of the dataset to be loaded

    Returns: The data
    """
    try:
        # First try to load from /tmp directory (for generated files)
        tmp_path = os.path.join(DATA_DIR, file)
        if os.path.exists(tmp_path):
            print(f"Loading file from temp directory: {tmp_path}")
            if '.csv' in tmp_path:
                return pd.read_csv(tmp_path)
            if '.parquet' in tmp_path:
                return pd.read_parquet(tmp_path)

        # If file doesn't exist in /tmp, try loading from deployment package
        deployment_path = os.path.join(get_deployment_package_path(), 'db_data', file)
        print(f"Attempting to load from deployment package: {deployment_path}")
        if os.path.exists(deployment_path):
            print(f"Loading file from deployment package: {deployment_path}")
            if '.csv' in deployment_path:
                return pd.read_csv(deployment_path)
            if '.parquet' in deployment_path:
                return pd.read_parquet(deployment_path)

        raise FileNotFoundError(f"File {file} not found in either {tmp_path} or {deployment_path}")

    except Exception as e:
        print(f"Error loading file {file}: {str(e)}")
        print(f"Current working directory: {os.getcwd()}")
        print(f"DATA_DIR contents: {os.listdir(DATA_DIR) if os.path.exists(DATA_DIR) else 'DIR NOT FOUND'}")
        print(f"Deployment package contents: {os.listdir(get_deployment_package_path()) if os.path.exists(get_deployment_package_path()) else 'DIR NOT FOUND'}")
        raise

def save_data(DATA_DIR, data, file, file_format='csv'):
    """
    Function to save the data to the temporary directory

    Args:
    DATA_DIR(str): The path where the data should be saved
    data(dataframe): The data to be saved
    file: The filename of the dataset to be saved
    file_format: The format to save the file in ('csv' or 'excel')

    Returns: Response
    """
    try:
        # Ensure the directory exists
        os.makedirs(DATA_DIR, exist_ok=True)
        
        if file_format == 'csv':
            path = os.path.join(DATA_DIR, f"{file}.csv")
            data.to_csv(path, index=None)
        elif file_format == 'excel':
            path = os.path.join(DATA_DIR, f"{file}.xlsx")
            data.to_excel(path, index=None)
        
        print(f"File saved successfully at: {path}")
        return "Files saved"
    except Exception as e:
        print(f"Error saving file {file}: {str(e)}")
        raise


# def log_error(src_module, error_msg):
#     """
#     Function to log errors to the temporary directory

#     Args:
#     src_module(str): The module from which the error arises
#     error_msg(str): The error message
#     """
#     try:
#         filepath = os.path.join(DATA_DIR, 'error_log.txt')
#         os.makedirs(DATA_DIR, exist_ok=True)
#         current_time = datetime.datetime.now()
#         with open(filepath, "a+", encoding="utf-8") as f:
#             message = f"Time of error:{current_time}, Error message: {error_msg}, Source Module: {src_module}\n"
#             f.write(message)
#             print("Error :",message)    
#         print(f"Error logged to: {filepath}")
#     except Exception as e:
#         print(f"Error logging to file: {str(e)}")
#         # Fall back to console logging if file logging fails
#         print(f"Error Log - Time: {datetime.datetime.now()}, Module: {src_module}, Error: {error_msg}")

def log_error(src_module, error_msg):
    """
    Function to log errors to the temporary directory

    Args:
    src_module(str): The module from which the error arises
    error_msg(str): The error message
    """
    try:
        # Initialize S3 client
        s3_client = boto3.client('s3')
        S3_BUCKET = os.environ.get("S3_BUCKET_NAME")
        if not S3_BUCKET:
            raise ValueError("S3_BUCKET_NAME environment variable is not set")
        current_time = datetime.datetime.now()
        filepath = os.path.join("log_files", str(current_time)+'_error_log.txt')
        message = f"Time of error:{current_time}, Error message: {error_msg}, Source Module in Data Analyst: {src_module}\n"
        s3_client.put_object(Bucket=S3_BUCKET,Key=filepath, Body=message)
        print(f"Error logged to: {filepath}")
    except Exception as e:
        print(f"Error logging to file: {str(e)}")
        print(f"Error Log - Time: {datetime.datetime.now()}, Module: {src_module}, Error: {error_msg}")


def extract_data(text_resp,tag1='<answer>',tag2='</answer>'):
    """
    Function to extract the relevant text output(SQL, natural langugae annswer) from LLM response

    Args:
    text_resp(str): The generated text from LLM
    tag1(str): The starting tag containing the relevant output
    tag2(str): The ending tag containing the relevant output

    Returns: Extracted output
    """
    
    text_resp = text_resp.strip()
    gen_text = text_resp.split(tag1)[1].split(tag2)[0]
    # gen_text = gen_text.replace('\n',' ').strip()
    #sql = sql.upper()
    return gen_text

def extract_py_code(text_resp):
    """
    Function to extract the relevant text output(python query) from LLM response

    Args:
    text_resp(str): The generated text from LLM

    Returns: Extracted python query
    """
    
    text_resp = text_resp.strip()
    gen_func = text_resp.split('<answer>')[1].split('</answer>')[0]
    return gen_func

def delay(dur):
    """
    Function to delay execution of code

    Args:
    dur(int): The duration for which the execution to be delyaed
    """
    end_time = time() + dur
    while True:
      now = time()
      #print('now', now)
      if now > end_time:
        break


# Helper function to verify file access
def verify_file_access(filepath):
    """Helper function to verify file access and permissions"""
    try:
        if os.path.exists(filepath):
            print(f"File exists at {filepath}")
            print(f"File permissions: {oct(os.stat(filepath).st_mode)[-3:]}")
            print(f"File size: {os.path.getsize(filepath)} bytes")
            return True
        else:
            print(f"File does not exist at {filepath}")
            print(f"Parent directory exists: {os.path.exists(os.path.dirname(filepath))}")
            print(f"Parent directory contents: {os.listdir(os.path.dirname(filepath))}")
            return False
    except Exception as e:
        print(f"Error checking file access: {str(e)}")
        return False

def verify_paths():
    """
    Helper function to verify and print path information
    """
    paths = {
        'Current Working Directory': os.getcwd(),
        'DATA_DIR': DATA_DIR,
        'Deployment Package Path': get_deployment_package_path(),
        '/tmp directory': '/tmp'
    }
    
    for name, path in paths.items():
        print(f"\n{name}: {path}")
        if os.path.exists(path):
            print(f"Exists: Yes")
            print(f"Contents: {os.listdir(path)}")
        else:
            print(f"Exists: No")


def log_error(src_module, error_msg):
    """
    Function to log errors to the temporary directory

    Args:
    src_module(str): The module from which the error arises
    error_msg(str): The error message
    """
    try:
        s3 = boto3.client('s3')
        S3_BUCKET = os.environ.get("S3_BUCKET_NAME")
        current_time = datetime.datetime.now()
        filepath = os.path.join("log_files", str(current_time)+'_error_log.txt')
        message = f"Time of error:{current_time}, Error message: {error_msg}, Source Module: {src_module}\n"
        s3.put_object(Bucket=S3_BUCKET,Key=filepath, Body=message)
        print(f"Error logged to: {filepath}")
    except Exception as e:
        print(f"Error logging to file: {str(e)}")
        print(f"Error Log - Time: {datetime.datetime.now()}, Module: {src_module}, Error: {error_msg}")