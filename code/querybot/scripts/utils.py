import sys
sys.path.insert(0, '../')

from scripts.config import AWS_REGION, LLM_CONF
from scripts.bedrock_llm import BedrockLLM
from scripts.sagemaker_llm import SageMakerLLM
import boto3
import botocore
from botocore.config import Config
import os
import logging
import json
import datetime
import time
import copy
import tarfile
from pathlib import Path
import shutil

# Configure logger
logger = logging.getLogger(__name__)

s3 = boto3.client('s3')
def get_bedrock_client(assumed_role=None, region='us-east-1', url_override = None):
    boto3_kwargs = {}
    session = boto3.Session()

    target_region = os.environ.get('AWS_DEFAULT_REGION',region)

    logging.debug(f"Create new client\n  Using region: {target_region}")
    if 'AWS_PROFILE' in os.environ:
        logging.debug(f"Using profile: {os.environ['AWS_PROFILE']}")

    retry_config = Config(
        region_name = target_region,
        retries = {
            'max_attempts': 10,
            'mode': 'standard'
        }
    )
    boto3_kwargs = {}

    if assumed_role:
        # logging.info(f"Using role: {assumed_role}", end='')
        sts = session.client("sts")
        response = sts.assume_role(
            RoleArn=str(assumed_role), #
            RoleSessionName="langchain-llm-1"
        )
        boto3_kwargs['aws_access_key_id']=response['Credentials']['AccessKeyId']
        boto3_kwargs['aws_secret_access_key']=response['Credentials']['SecretAccessKey']
        boto3_kwargs['aws_session_token']=response['Credentials']['SessionToken']

    if url_override:
        boto3_kwargs['endpoint_url']=url_override

    bedrock_client = session.client(
        service_name='bedrock-runtime',
        config=retry_config,
        region_name= target_region,
        **boto3_kwargs
        )

    logging.debug("boto3 Bedrock client successfully created!")
    logging.debug(bedrock_client._endpoint)
    return bedrock_client


# def init_llm(modelId):
#     boto3_bedrock_client = get_bedrock_client(
#         region=AWS_REGION, 
#         )

#     llm = Bedrock(
#         client=boto3_bedrock_client, 
#         model_id=modelId,
#         model_kwargs=LLM_CONF[modelId]
#     )
#     return llm


def init_bedrock_llm(modelId: str, model_args: dict|None = None) -> BedrockLLM:
    model_kwargs = copy.deepcopy(LLM_CONF[modelId])
    if model_args is not None:
        model_kwargs.update(model_args)
    return BedrockLLM(model_id=modelId, region_name=AWS_REGION, **model_kwargs)

def init_sagemaker_llm(model_id: str) -> SageMakerLLM:
    return SageMakerLLM(endpoint_name='data-analyst-endpoint-1', inference_component_name=model_id, region_name=AWS_REGION)

def make_tarfile(output_file_path, source_dir):
    with tarfile.open(output_file_path, "w:gz") as tar:
        tar.add(source_dir, arcname=os.path.basename(source_dir))


def delete_files(path):
    try:
        shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
    except Exception as e:
        print(f'Failed to delete file / directory: {e}')


# def create_sm_model(sm_client, role, inference_image_uri, 
#                     s3_code_artifact, model_name):
#     #model_name = name_from_base(f"codellama-djl")
#     model_name = name_from_base(model_name)
#     print(model_name)
#     create_model_response = sm_client.create_model(
#         ModelName=model_name,
#         ExecutionRoleArn=role,
#         PrimaryContainer={
#             "Image": inference_image_uri,
#             "ModelDataUrl": s3_code_artifact,
#             "Environment": {"MODEL_LOADING_TIMEOUT": "3600"},
#         },
#     )
#     model_arn = create_model_response["ModelArn"]
#     print(f"Created Model: {model_arn}")
#     return model_name


def create_sm_endpoint_conf(sm_client, model_name, instanceType):
    endpoint_config_name = f"{model_name}-config"
    endpoint_config_response = sm_client.create_endpoint_config(
        EndpointConfigName=endpoint_config_name,
        ProductionVariants=[
            {
                "VariantName": "variant1",
                "ModelName": model_name,
                "InstanceType": instanceType,
                "InitialInstanceCount": 1,
                "ModelDataDownloadTimeoutInSeconds": 1800,
                "ContainerStartupHealthCheckTimeoutInSeconds": 1800,
            },
        ],
    )
    print (endpoint_config_response)
    return endpoint_config_name
    
def create_sm_endpoint(sm_client, model_name, endpoint_config_name):
    endpoint_name = f"{model_name}-endpoint"
    create_endpoint_response = sm_client.create_endpoint(
        EndpointName=f"{endpoint_name}", EndpointConfigName=endpoint_config_name
    )
    print(f"Created Endpoint: {create_endpoint_response['EndpointArn']}")

    resp = sm_client.describe_endpoint(EndpointName=endpoint_name)
    status = resp["EndpointStatus"]
    print("Status: " + status)
    while status == "Creating":
        time.sleep(60)
        resp = sm_client.describe_endpoint(EndpointName=endpoint_name)
        status = resp["EndpointStatus"]
        print("Status: " + status)

    print("Arn: " + resp["EndpointArn"])
    print("Status: " + status)
    return endpoint_name


def deploy_sm_lmi_model(model_name, inference_image_uri, s3_code_artifact,
                        sm_client, role, instanceType):
    
    # model_name = create_sm_model(sm_client, role, inference_image_uri, 
    #                              s3_code_artifact, model_name)
    endpoint_config_name = create_sm_endpoint_conf(sm_client, 
                                                   model_name, instanceType)
    endpoint_name = create_sm_endpoint(sm_client, 
                                       model_name, endpoint_config_name)
    
    return endpoint_name, endpoint_config_name, model_name
    
    
def cleanup_inference_resources(sm_client, endpoint_name, endpoint_config_name, model_name):
    try:
        sm_client.delete_endpoint(EndpointName=endpoint_name)
    except Exception as e:
        logger.warning(f"Endpoint {endpoint_name} not found!")
    sm_client.delete_endpoint_config(EndpointConfigName=endpoint_config_name)
    sm_client.delete_model(ModelName=model_name)


def get_model_loc(s3_path, bucket):
    file = s3_path.split("/")[-1]
    dir_path = s3_path[s3_path.index(bucket)+len(bucket)+1 : s3_path.rindex(file)-1]
    return file, dir_path


def split_s3_path(s3_path):
    path_parts=s3_path.lower().replace("s3://","").split("/")
    bucket=path_parts.pop(0)
    key="/".join(path_parts)
    return bucket, key


def copy_across_s3_buckets(src_bucke_name, src_obj_key, dest_bucket_name, dest_obj_key):
    s3 = boto3.Session().resource('s3')
    dest_bucket = s3.Bucket(dest_bucket_name)
    dest_bucket.copy({
        'Bucket': src_bucke_name,
        'Key': src_obj_key
        }, 
        dest_obj_key
        )
    print('Object copied')

def s3_key_exists(bucket, key):
    key_exists = True
    try:
        s3.head_object(Bucket=bucket, Key=key)
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "404":
            key_exists = False
    return key_exists

def delete_from_s3(bucket, key):
    s3 = boto3.Session().resource('s3')
    bucket = s3.Bucket(bucket)
    bucket.object_versions.filter(Prefix=key).delete()

def get_embedding(text, embedding_model_id):

    bedrock = boto3.client(
    service_name='bedrock-runtime')

    if 'cohere' in embedding_model_id:
        body = json.dumps({
        "texts": [text],
        "input_type": "search_query",
        "truncate": "END",
        "embedding_types": ["float"]
    })
    else:
        body = json.dumps({
            "inputText": text,
            "embeddingTypes": ["float"]
        })

    print('Embedding Model ID:', embedding_model_id)

    response = bedrock.invoke_model(
        body=body,
        modelId=embedding_model_id,
        accept='application/json',
        contentType='application/json'
    )
    
    response_body = json.loads(response['body'].read())
    if 'cohere' in embedding_model_id:
        return response_body['embeddings']['float'][0]
    
    return response_body['embedding']

def log_error(src_module, error_msg):
    """
    Function to log errors to the temporary directory

    Args:
    src_module(str): The module from which the error arises
    error_msg(str): The error message
    """
    try:
        S3_BUCKET = os.environ.get("S3_BUCKET_NAME")
        current_time = datetime.datetime.now()
        filepath = os.path.join("log_files", str(current_time)+'_error_log.txt')
        message = f"Time of error:{current_time}, Error message: {error_msg}, Source Module: {src_module}\n"
        s3.put_object(Bucket=S3_BUCKET,Key=filepath, Body=message)
        print(f"Error logged to: {filepath}")
    except Exception as e:
        print(f"Error logging to file: {str(e)}")
        print(f"Error Log - Time: {datetime.datetime.now()}, Module: {src_module}, Error: {error_msg}")