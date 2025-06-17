# © 2023 Amazon Web Services, Inc. or its affiliates. All Rights Reserved.

# This AWS Content is provided subject to the terms of the AWS Customer Agreement
# available at http://aws.amazon.com/agreement or other written agreement between
# Customer and either Amazon Web Services, Inc. or Amazon Web Services EMEA SARL or both.

# License terms can be found at: https://aws.amazon.com/legal/aws-ip-license-terms/

import sys
sys.path.insert(0, '../')

import logging
import time
import yaml
import argparse
import os
import sagemaker
import boto3
from datasets import Dataset
import pandas as pd
from itertools import chain
from functools import partial
from transformers import AutoTokenizer
from sagemaker.huggingface import HuggingFace
from config import S3_BUCKET, AWS_REGION, MODELS_DIR, DB_CONF_PATH, SUPPORTED_HF_LLMS, HF_LLM_PROMPT_KEYS
from scripts.prompts import LLM_ZS_PROMPTS
from scripts.sql.executor import get_database_helper
from utils import split_s3_path, copy_across_s3_buckets, delete_from_s3
from sagemaker.s3 import S3Downloader

logging.basicConfig(level=logging.INFO)

os.environ['AWS_DEFAULT_REGION'] = AWS_REGION
# empty list to save remainder from batches to use in next batch
remainder = {"input_ids": [], "attention_mask": [], "token_type_ids": []}

def chunk(sample, chunk_length=2048):

    global remainder
    concatenated_examples = {k: list(chain(*sample[k])) for k in sample.keys()}
    concatenated_examples = {k: remainder[k] + concatenated_examples[k] for k in concatenated_examples.keys()}
    batch_total_length = len(concatenated_examples[list(sample.keys())[0]])

    if batch_total_length >= chunk_length:
        batch_chunk_length = (batch_total_length // chunk_length) * chunk_length

    result = {
        k: [t[i : i + chunk_length] for i in range(0, batch_chunk_length, chunk_length)]
        for k, t in concatenated_examples.items()
    }
    remainder = {k: concatenated_examples[k][batch_chunk_length:] for k in concatenated_examples.keys()}
    result["labels"] = result["input_ids"].copy()
    return result

def get_schema(database_name):

    with open(DB_CONF_PATH, 'r') as file:
        db_conf = yaml.safe_load(file)
    conf = db_conf[database_name]
    database_type = conf['database_type']
    db_conn_conf = conf['db_conn_conf']
    db_schema_file = conf['db_schema_file']
    db_helper =  get_database_helper(database_type, db_conn_conf, 
                                     None, None, None, 0, db_schema_file)
    db_schema = db_helper.get_schema_info()
    return database_type, db_schema

def prep_training_dataset(config):

    model_id = config["model_id"]
    database_type, schema = get_schema(config['database_name'])
    training_data_path = config['training_data_file']
    s3_bucket, s3_key = split_s3_path(config['training_s3_loc'])
    template = LLM_ZS_PROMPTS[HF_LLM_PROMPT_KEYS[model_id]]

    tokenizer = AutoTokenizer.from_pretrained(model_id)
    tokenizer.pad_token = tokenizer.eos_token
    is_train=True

    def create_prompt(sample):
        sql = f'{sample["query"]}{tokenizer.eos_token}' if is_train else ""
        prompt = template.format(sql_database=database_type,
            schema=schema, question=sample["question"], query=sql)
        sample["prompt"] = prompt
        return sample

    dataset = Dataset.from_pandas(pd.read_csv(training_data_path))
    dataset = dataset.map(create_prompt, remove_columns=list(dataset.features))
    lm_dataset = dataset.map(
        lambda sample: tokenizer(sample["prompt"]), batched=True, remove_columns=list(dataset.features)
    ).map(
        partial(chunk, chunk_length=1024),
        batched=True,
    )
    logging.info(f"Total number of samples: {len(lm_dataset)}")
    training_s3_loc = f"s3://{s3_bucket}/{s3_key}"
    delete_from_s3(s3_bucket, s3_key)
    lm_dataset.save_to_disk(training_s3_loc)
    return lm_dataset

def set_session(sagemaker_session_bucket=None, role=None, region=None):

    sess = sagemaker.Session()
    if sagemaker_session_bucket is None and sess is not None:
        sagemaker_session_bucket = sess.default_bucket()
    try:
        role = sagemaker.get_execution_role()
    except ValueError:
        iam = boto3.client('iam')
        role = iam.get_role(RoleName='sagemaker_execution_role')['Role']['Arn']
    sess = sagemaker.Session(default_bucket=sagemaker_session_bucket)
    logging.info(f"sagemaker role arn: {role}")
    logging.info(f"sagemaker bucket: {sagemaker_session_bucket}")
    logging.info(f"sagemaker session region: {sess.boto_region_name}")


def start_training_sm(sm_finetuning_config_file):

    sess = sagemaker.Session(default_bucket=S3_BUCKET)
    try:
        role = sagemaker.get_execution_role()
    except ValueError:
        iam = boto3.client("iam")
        role = iam.get_role(RoleName="sagemaker_execution_role")["Role"]["Arn"]

    logging.info(f"sagemaker role arn: {role}")
    logging.info(f"sagemaker bucket: {sess.default_bucket()}")
    logging.info(f"sagemaker session region: {sess.boto_region_name}")

    # define Training Job Name
    job_name = f'huggingface-qlora-{time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())}'

    with open(sm_finetuning_config_file, 'r') as file:
        config = yaml.safe_load(file)

    sm_training_config = config['SageMaker Training Config']
    training_hyperparameters = config['Training Hyperparameters']

    if sm_training_config["model_id"] != training_hyperparameters["model_id"]:
        raise ValueError("Model IDs in Training Config and Hyperparameters do not match!")

    if sm_training_config["model_id"] not in SUPPORTED_HF_LLMS:
        raise ValueError(f"model_id {sm_training_config['model_id']} is not supported! Supported Huggingface models are: {SUPPORTED_HF_LLMS}")

    prep_training_dataset(sm_training_config)

    # create the Estimator
    huggingface_estimator = HuggingFace(hyperparameters=training_hyperparameters,
                                        base_job_name=job_name,
                                        role=role,
                                        **sm_training_config)
    # define a data input dictonary with our uploaded s3 uris
    data = {'training': sm_training_config["training_s3_loc"], 'val': sm_training_config["val_s3_loc"]}
    # starting the train job with our uploaded datasets as input
    huggingface_estimator.fit(data, wait=True)

    src_bucket, src_key = split_s3_path(huggingface_estimator.model_data)
    dest_bucket, dest_key = split_s3_path(sm_training_config["model_destination_path"])
    
    S3Downloader.download(
        s3_uri=huggingface_estimator.model_data, # S3 URI where the trained model is located
        local_path=MODELS_DIR,                   # local path where *.targ.gz is saved
        sagemaker_session=sess                   # SageMaker session used for training the model
    )

    copy_across_s3_buckets(src_bucket, src_key, dest_bucket, dest_key)
    logging.info(f"Finetuned model exported at {sm_training_config['model_destination_path']}")

def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ft_config_path", type=str, default="../conf/finetuning_config.yaml", help="Path to finetuning coniguration yaml.")
    args, _ = parser.parse_known_args()
    #set_session(bucket, role_arn, region)
    start_training_sm(args.ft_config_path)   
    
if __name__ == "__main__":
    run()
