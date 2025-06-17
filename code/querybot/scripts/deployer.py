# © 2023 Amazon Web Services, Inc. or its affiliates. All Rights Reserved.

# This AWS Content is provided subject to the terms of the AWS Customer Agreement
# available at http://aws.amazon.com/agreement or other written agreement between
# Customer and either Amazon Web Services, Inc. or Amazon Web Services EMEA SARL or both.

# License terms can be found at: https://aws.amazon.com/legal/aws-ip-license-terms/

import sys

sys.path.insert(0, '../')
import logging
from scripts.utils import make_tarfile, delete_files, \
deploy_sm_lmi_model, get_model_loc, s3_key_exists, delete_from_s3
from scripts.config import AWS_REGION, MODELS_DIR
import argparse
import sagemaker
from sagemaker import image_uris
import boto3
import os
import yaml
import tarfile
from pathlib import Path
from sagemaker.huggingface import HuggingFaceModel
import boto3
import os

logging.basicConfig(level=logging.INFO)
os.environ['AWS_DEFAULT_REGION'] = AWS_REGION


def write_djl_serving_props(temp_local_dir, lmi_framework, s3_model_artifact):
    lmi_options = {}
    # Common params
    lmi_options['engine'] = 'MPI'
    lmi_options['option.model_id'] = s3_model_artifact
    lmi_options['option.tensor_parallel_degree'] = 4
    lmi_options['option.output_formatter'] = 'json'
    lmi_options['option.max_rolling_batch_size'] = 32
    lmi_options['option.model_loading_timeout'] = 1800

    if lmi_framework == 'djl-tensorrtllm':
        lmi_options['option.use_custom_all_reduce'] = 'true'
        lmi_options['option.max_input_len'] = 4096
        lmi_options['option.max_output_len'] = 1024
    elif lmi_framework == 'djl-deepspeed':
        lmi_options['option.task'] = 'text-generation'
        lmi_options['option.rolling_batch'] = 'lmi-dist'
        lmi_options['option.max_tokens'] = 5120
    else:
        raise ValueError(f"LMI Framework {lmi_framework} not supported!")

    target_file = f"{temp_local_dir}/serving.properties"
    os.makedirs(os.path.dirname(target_file), exist_ok=True)
    with open(target_file, 'w') as f:
        for key in lmi_options:
            f.write(f"{key} = {lmi_options[key]}\n")


def check_and_upload(sess, s3_bucket, s3_key, model_download_path, replace_existing_model_data):

    if s3_key_exists(s3_bucket, s3_key):
        if replace_existing_model_data:
            delete_from_s3(s3_bucket, s3_key)
        else:
            raise ValueError(f"{s3_key} already exists in {s3_bucket} S3 bucket! \
                                 Set config param 'replace_existing_model_data' to True and re-run.")
    s3_model_artifact = sess.upload_data(path=model_download_path, key_prefix=s3_key)
    return s3_model_artifact


def delete_existing_local_model_dir(model_download_path, replace_existing_model_data):
    if replace_existing_model_data:
        delete_files(model_download_path)
    elif os.path.isdir(model_download_path):
        raise ValueError(f"'{model_download_path}' already exists in local files ystem! \
                                 Set config param 'replace_existing_model_data' to True and re-run.")


def upload_finetuned_model_data(sess, model_id, s3_bucket, s3_destination_prefix, replace_existing_model_data):


    def get_tar_data(tarf):
        members = [fn for fn in tarf.getmembers() if os.path.abspath(os.path.join(model_download_path, fn)).startswith(model_download_path)]
        return members

    model_download_path = f'{MODELS_DIR}/finetuned_model_artefacts/'
    delete_existing_local_model_dir(model_download_path, replace_existing_model_data)

    finetuned_model_file, s3_dir_path = get_model_loc(model_id, s3_bucket)
    downloaded_finetuned_model_file = f"{MODELS_DIR}/{finetuned_model_file}"

    # logging.info(s3_bucket, f"{s3_dir_path}/{finetuned_model_file}")
    boto3.client("s3").download_file(s3_bucket, f"{s3_dir_path}/{finetuned_model_file}",
                                     downloaded_finetuned_model_file)
    tarf = tarfile.open(downloaded_finetuned_model_file)
    try:
        tarf.extractall(model_download_path, 
                        members=get_tar_data(tarf))
    except Exception as e:
        raise e
    finally:
        tarf.close()
        
    s3_key = f"{s3_destination_prefix}/finetuned_model_artefacts"
    s3_model_artifact = check_and_upload(sess, s3_bucket, s3_key, model_download_path, replace_existing_model_data)
    # s3_destination_finetuned = f"{s3_destination_prefix}/finetuned_model"

    # if s3_key_exists(sess, s3_bucket, s3_destination_finetuned):
    #     if replace_existing_model_data:
    #         delete_from_s3(sess, s3_bucket, s3_destination_finetuned)
    #     else:
    #         raise ValueError(f"{s3_destination_finetuned} already exists in {s3_bucket} S3 bucket! \
    #                          Set config param 'replace_existing_model_data' to True and re-run.")

    # s3_model_artifact = sess.upload_data(path=f'./{extracted_finetuned_model_dir}',
    #                                      key_prefix=s3_destination_finetuned)
    return s3_model_artifact


def upload_pretrained_hf_model_data(sess, model_id, s3_bucket, s3_destination_prefix, replace_existing_model_data):
    from huggingface_hub import snapshot_download
    from pathlib import Path

    # - This will download the model into the current directory where ever the jupyter notebook is running
    local_model_path = Path(MODELS_DIR)
    local_model_path.mkdir(exist_ok=True)
    # Only download pytorch checkpoint files
    allow_patterns = ["*.json", "*.pt", "*.bin", "*.txt", "*.model", "*.safetensors"]
    delete_existing_local_model_dir(local_model_path, replace_existing_model_data)

    # - Leverage the snapshot library to donload the model since the model is stored in repository using LFS
    model_download_path = snapshot_download(
        repo_id=model_id,
        cache_dir=local_model_path,
        allow_patterns=allow_patterns,
    )
    s3_key = f"{s3_destination_prefix}/pretrained_model_artefacts"
    s3_model_artifact = check_and_upload(sess, s3_bucket, s3_key, model_download_path, replace_existing_model_data)

    # s3_destination_pretrained = f"{s3_destination_prefix}/pretrained_model"
    # # define a variable to contain the s3url of the location that has the model
    # logging.info(f"Pretrained model will be uploaded to ---- > s3://{s3_bucket}/{s3_destination_pretrained}/")

    # if s3_key_exists(sess, s3_bucket, s3_destination_pretrained):
    #     if replace_existing_model_data:
    #         delete_from_s3(sess, s3_bucket, s3_destination_pretrained)
    #     else:
    #         raise ValueError(f"{s3_destination_pretrained} already exists in {s3_bucket} S3 bucket! \
    #                          Set config param 'replace_existing_model_data' to True and re-run.")

    # s3_model_artifact = sess.upload_data(path=model_download_path, key_prefix=s3_destination_pretrained)
    return s3_model_artifact


def deploy_scaled(model_id,
                  model_name,
                  lmi_framework,
                  s3_bucket,
                  s3_destination_prefix,
                  replace_existing_model_data,
                  instanceType,
                  finetuned_model=True):

    role = sagemaker.get_execution_role()  # execution role for the endpoint
    sess = sagemaker.session.Session(
        default_bucket=s3_bucket)  # sagemaker session for interacting with different AWS APIs
    bucket = sess.default_bucket()  # bucket to house artifacts
    model_bucket = sess.default_bucket()  # bucket to house artifacts
    region = sess._region_name
    account_id = sess.account_id()
    sm_client = boto3.client("sagemaker")
    smr_client = boto3.client("sagemaker-runtime")

    upload_func = upload_finetuned_model_data if finetuned_model else upload_pretrained_hf_model_data
    s3_model_artifact = upload_func(sess, model_id, s3_bucket, s3_destination_prefix, replace_existing_model_data)

    logging.info(f"Model uploaded to --- > {s3_model_artifact}")
    logging.info(f"We will set option.model_id={s3_model_artifact}")

    temp_local_dir = f"{MODELS_DIR}/model_artefacts_{model_name}"
    write_djl_serving_props(temp_local_dir, lmi_framework, s3_model_artifact)

    inference_image_uri = sagemaker.image_uris.retrieve(framework=lmi_framework, region=region, version='0.25.0')
    logging.info(f"Image going to be used is ---- > {inference_image_uri}")

    output_file_path = f"{MODELS_DIR}/model.tar.gz"
    delete_files(output_file_path)
    delete_files(f"{temp_local_dir}/.ipynb_checkpoints")
    make_tarfile(output_file_path, temp_local_dir)

    s3_code_artifact = sess.upload_data(output_file_path, bucket, s3_destination_prefix)
    logging.info(f"S3 Code or Model tar ball uploaded to --- > {s3_code_artifact}")

    delete_files(temp_local_dir)
    delete_files(output_file_path)

    endpoint_name, endpoint_config_name, model_name = deploy_sm_lmi_model(model_name, inference_image_uri,
                                                                          s3_code_artifact, sm_client, role,
                                                                          instanceType)
    return endpoint_name, endpoint_config_name, model_name


def deploy(model_name: str, model_id: str, instance_type: str):
    sess = sagemaker.Session()
    # sagemaker session bucket -> used for uploading data, models and logs
    # sagemaker will automatically create this bucket if it not exists
    sagemaker_session_bucket = None
    region = sess._region_name
    if sagemaker_session_bucket is None and sess is not None:
        # set to default bucket if a bucket name is not given
        sagemaker_session_bucket = sess.default_bucket()

    try:
        role = sagemaker.get_execution_role()
    except ValueError:
        iam = boto3.client('iam')
        role = iam.get_role(RoleName='sagemaker_execution_role')['Role']['Arn']

    sess = sagemaker.Session(default_bucket=sagemaker_session_bucket)

    logging.info(f"sagemaker role arn: {role}")
    logging.info(f"sagemaker bucket: {sess.default_bucket()}")
    logging.info(f"sagemaker session region: {sess.boto_region_name}")

    llm_image = sagemaker.image_uris.retrieve("djl-deepspeed", region=region, version="0.25.0")

    # create HuggingFaceModel with the image uri
    llm_model = HuggingFaceModel(
        model_data=model_id,
        #image_uri=llm_image,
        transformers_version="4.37.0",
        pytorch_version="2.1.0",  # pytorch version used
        py_version="py310",  # python version of the DLC
        model_server_workers=1,
        role=role,
        sagemaker_session=sess,
    )

    endpoint_name = f"{model_name}-endpoint"
    llm_model.deploy(
        initial_instance_count=1,
        instance_type=instance_type,
        endpoint_name=endpoint_name,
    )
    return endpoint_name


#python deployer.py --deployment_config_file "conf/deployment_config.yaml" --djl_deployment True

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--deployment_config_file",
                        type=str,
                        default="../conf/deployment_config.yaml",
                        help="Path to deployment coniguration yaml.")
    parser.add_argument("--djl_deployment",
                        type=str,
                        default="Y",
                        help="Whether to use SageMaker Large Model Inference using DJL.")
    args, _ = parser.parse_known_args()
    deployment_config_file = args.deployment_config_file
    djl_deployment = args.djl_deployment

    assert djl_deployment in ["Y", "N"], f'djl_deployment value should be one of ["Y", "N"]'

    logging.info(f"deployment_config_file: {deployment_config_file}")
    logging.info(f"djl_deployment: {djl_deployment}")

    with open(deployment_config_file, 'r') as file:
        config = yaml.safe_load(file)

    if djl_deployment.upper() == "Y":
        conf = config['LMI Deployment Config']
        endpoint_name, endpoint_config_name, model_name = deploy_scaled(conf['model_id'],
                                                                        conf['model_name'],
                                                                        conf['lmi_framework'],
                                                                        conf['s3_bucket'],
                                                                        conf['s3_destination_prefix'],
                                                                        conf['replace_existing_model_data'],
                                                                        conf['instanceType'],
                                                                        finetuned_model=conf['finetuned_model'])
    else:
        conf = config['Deployment Config']
        endpoint_name = deploy(conf['model_id'], conf['model_id'], conf['instance_type'])

    with open(conf["sm_endpoint_name_export_file"], 'w') as f:
        f.write(endpoint_name.strip())

    logging.info(f'Deployment of endpoint {endpoint_name} completed!')
