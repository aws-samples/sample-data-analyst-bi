import sys

sys.path.insert(0, '../')

import boto3
from botocore.exceptions import ClientError
import time
import os
import pandas as pd
import json
import yaml
import argparse
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
from langchain_community.vectorstores import OpenSearchVectorSearch
from langchain_community.embeddings import BedrockEmbeddings
from langchain_community.document_loaders import DataFrameLoader
from scripts.utils import get_bedrock_client
from scripts.config import AWS_REGION, VPCE_ID

os.environ['AWS_DEFAULT_REGION'] = AWS_REGION

BEDROCK_RUNTIME = boto3.client(
    service_name='bedrock-runtime',
    region_name=AWS_REGION,
)


def get_embeddings(text, emb_model_id='amazon.titan-embed-text-v1'):
    body = json.dumps({
        "inputText": text,
    })
    response = BEDROCK_RUNTIME.invoke_model(body=body,
                                            modelId=emb_model_id,
                                            accept='application/json',
                                            contentType='application/json')
    response_body = json.loads(response['body'].read())
    embedding = response_body.get('embedding')
    return embedding


def handle_conflict_exception(e, object_type, name, category=None):
    if e.response['Error']['Code'] == 'ConflictException':
        msg = f"{object_type} with name {name} already exists"
        if category is not None:
            msg = f"{object_type} with name {name} and type {category} already exists"
    else:
        msg = f"Unexpected error: {e}"
    print(msg)


def setup_opensearch(vector_store_name,
                     encryption_policy_name="bedrock-workshop-rag-sp",
                     network_policy_name="bedrock-workshop-rag-np",
                     access_policy_name="bedrock-workshop-rag-ap"):

    identity = boto3.client('sts').get_caller_identity()['Arn']

    aoss_client = boto3.client('opensearchserverless')

    try:
        security_policy = aoss_client.create_security_policy(name=encryption_policy_name,
                                                             policy=json.dumps({
                                                                 'Rules': [{
                                                                     'Resource': ['collection/' + vector_store_name],
                                                                     'ResourceType':
                                                                     'collection'
                                                                 }],
                                                                 'AWSOwnedKey':
                                                                 True
                                                             }),
                                                             type='encryption')
    except ClientError as e:
        handle_conflict_exception(e, 'Security Policy', encryption_policy_name, 'encryption')

    try:
        network_policy = aoss_client.create_security_policy(name=network_policy_name,
                                                            policy=json.dumps([{
                                                                'Rules': [{
                                                                    'Resource': ['collection/' + vector_store_name],
                                                                    'ResourceType':
                                                                    'collection'
                                                                }],
                                                                'AllowFromPublic':False, 
                                                                'SourceVPCEs':[VPCE_ID], 
                                                                'SourceServices':["bedrock.amazonaws.com"]
                                                            }]),
                                                            type='network')
    except ClientError as e:
        handle_conflict_exception(e, 'Security Policy', network_policy_name, 'network')

    collection = None
    try:
        collection = aoss_client.create_collection(name=vector_store_name, type='VECTORSEARCH')
        print(f"Collection ID: {collection['createCollectionDetail']['id']}")
    except ClientError as e:
        handle_conflict_exception(e, 'Collection', vector_store_name)

    if collection is not None:
        while True:
            status = aoss_client.list_collections(
                collectionFilters={'name': vector_store_name})['collectionSummaries'][0]['status']
            if status in ('ACTIVE', 'FAILED'): break
            time.sleep(10)

    try:
        access_policy = aoss_client.create_access_policy(name=access_policy_name,
                                                         policy=json.dumps([{
                                                             'Rules': [{
                                                                 'Resource': ['collection/' + vector_store_name],
                                                                 'Permission': [
                                                                     'aoss:CreateCollectionItems',
                                                                     'aoss:DeleteCollectionItems',
                                                                     'aoss:UpdateCollectionItems',
                                                                     'aoss:DescribeCollectionItems'
                                                                 ],
                                                                 'ResourceType':
                                                                 'collection'
                                                             }, {
                                                                 'Resource': ['index/' + vector_store_name + '/*'],
                                                                 'Permission': [
                                                                     'aoss:CreateIndex', 'aoss:DeleteIndex',
                                                                     'aoss:UpdateIndex', 'aoss:DescribeIndex',
                                                                     'aoss:ReadDocument', 'aoss:WriteDocument'
                                                                 ],
                                                                 'ResourceType':
                                                                 'index'
                                                             }],
                                                             'Principal': [identity],
                                                             'Description':
                                                             'Easy data policy'
                                                         }]),
                                                         type='data')
    except ClientError as e:
        handle_conflict_exception(e, 'Access Policy', access_policy_name, 'data')
    time.sleep(60)

    host = None
    if collection is not None:
        host = collection['createCollectionDetail']['id'] + '.' + os.environ.get("AWS_DEFAULT_REGION",
                                                                                 None) + '.aoss.amazonaws.com:443'
        print(f"Setup completed! OpenSearch url: {host}")
    else:
        print(
            f"Resources already exist! Either use the existing index or run indexing with 'delete_all_conflicts' set to Y"
        )

    return host


def index_docs_opensearch(host, index_name, df_docs, text_col="question"):

    loader = DataFrameLoader(df_docs, page_content_column=text_col)
    docs = loader.load()

    bedrock_embeddings = BedrockEmbeddings(client=get_bedrock_client(region=AWS_REGION))

    service = 'aoss'
    credentials = boto3.Session().get_credentials()
    auth = AWSV4SignerAuth(credentials, AWS_REGION, service)

    try:
        docsearch = OpenSearchVectorSearch.from_documents(
            docs,
            bedrock_embeddings,
            opensearch_url=host,
            http_auth=auth,
            timeout=100,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            index_name=index_name,
            engine="faiss",
        )
    except Exception as e:
        print (f"Indexing Error: {e}")


def search_opensearch(query, openSearch_endpoint, index_name, k=5):

    bedrock_embeddings = BedrockEmbeddings(client=get_bedrock_client(region=AWS_REGION))
    service = 'aoss'
    credentials = boto3.Session().get_credentials()
    auth = AWSV4SignerAuth(credentials, os.environ.get("AWS_DEFAULT_REGION", None), service)

    #print ("* * * * QUERY", query)
    #print (openSearch_endpoint, index_name)

    # Init OpenSearch client connection
    docsearch = OpenSearchVectorSearch(
        embedding_function=bedrock_embeddings,
        opensearch_url=openSearch_endpoint,
        http_auth=auth,
        timeout=100,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        index_name=index_name,
        engine="faiss",
    )
    docs = docsearch.similarity_search_with_score(query, k=k)
    #print (docs)

    hits = []
    questions = []
    for (doc, score) in docs:
        if doc.page_content.lower() not in questions:
            hits.append({'question': doc.page_content, 'query': doc.metadata['query'], 'score': score})
            questions.append(doc.page_content.lower())
    return hits


# def search_index(index_name, query):
#     results = docsearch.similarity_search(query, k=3)  # our search query  # return 3 most relevant docs
#     #print(dumps(results, pretty=True))
#     return results


def list_aoss_collections(collection_name=None):
    aoss_client = boto3.client('opensearchserverless')
    if collection_name is not None:
        collections = aoss_client.list_collections(collectionFilters={'name': collection_name})
    else:
        collections = aoss_client.list_collections()
    return collections


def delete_opensearch_collection(collection_name):
    aoss_client = boto3.client('opensearchserverless')
    collections = list_aoss_collections(collection_name=collection_name)['collectionSummaries']
    # print(collections)
    for collection in collections:
        try:
            print(collection_name, collection, collection['id'])
            aoss_client.delete_collection(id=collection['id'])
            while True:
                collections = list_aoss_collections(collection_name=collection_name)['collectionSummaries']
                if len(collections) == 0: break
                time.sleep(5)
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                print(f"Collection {collection['id']} does not exist.")


def delete_opensearch_permissions(access_policy_name, encryption_policy_name, network_policy_name):
    aoss_client = boto3.client('opensearchserverless')

    def handle_deletion(func, name, type):
        try:
            func(name=name, type=type)
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                print(f'Resource {name} of type {type} does not exist.')

    handle_deletion(aoss_client.delete_access_policy, access_policy_name, 'data')
    handle_deletion(aoss_client.delete_security_policy, encryption_policy_name, 'encryption')
    handle_deletion(aoss_client.delete_security_policy, network_policy_name, 'network')


def delete_opensearch_index(openSearch_endpoint, index_name):
    service = 'aoss'
    credentials = boto3.Session().get_credentials()
    auth = AWSV4SignerAuth(credentials, AWS_REGION, service)
    client = OpenSearch(
        hosts=[openSearch_endpoint],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
    )
    try:
        response = client.indices.delete(index=index_name)
    except Exception as e:
        response = e
        print(response)
    return response


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--indexing_config_file",
                        type=str,
                        default="../conf/indexing_config.yaml",
                        help="Path to indexing coniguration yaml.")
    parser.add_argument("--purpose",
                        type=str,
                        default='setup',
                        help="Whether the purpose is setup or indexing. [setup / indexing]")
    parser.add_argument("--delete_all_conflicts",
                        type=str,
                        default="N",
                        help="Whether to delete all conflicting index and permissions. [N / Y]")
    args, _ = parser.parse_known_args()
    indexing_config_file = args.indexing_config_file
    purpose = args.purpose
    delete_all_conflicts = args.delete_all_conflicts

    assert purpose in ["setup", "indexing"], f'delete_all_conflicts value should be one of ["Y", "N"]'
    assert delete_all_conflicts in ["Y", "N"], f'delete_all_conflicts value should be one of ["Y", "N"]'

    print(f"indexing_config_file: {indexing_config_file}")
    print(f"purpose: {purpose}")
    print(f"delete_all_conflicts: {delete_all_conflicts}")

    with open(indexing_config_file, 'r') as file:
        config = yaml.safe_load(file)["OpenSearch Config"]

    if purpose == 'setup':
        if delete_all_conflicts.upper() == "Y":
            print("Deleting conflicting resources . . . . .")
            #if len(config["open_search_host_url"].strip())>0:
            #    delete_opensearch_index(config["open_search_host_url"], config["aoss_index_name"])
            delete_opensearch_collection(config["aoss_vector_store_name"])
            delete_opensearch_permissions(config["aoss_access_policy_name"], config["aoss_encryption_policy_name"],
                                          config["aoss_network_policy_name"])

        print("Setting up OpenSearch for indexing . . . . .")
        host = setup_opensearch(config["aoss_vector_store_name"],
                                encryption_policy_name=config["aoss_encryption_policy_name"],
                                network_policy_name=config["aoss_network_policy_name"],
                                access_policy_name=config["aoss_access_policy_name"])

        #host = "hssmhi8ivydoysnyi2gj.us-east-1.aoss.amazona1ws.com:443"
        if host is not None:
            with open(config["host_url_export_file"], 'w') as outputfile:
                yaml.dump({
                    "aoss_host": host,
                    "aoss_index_name": config["aoss_index_name"]
                },
                          outputfile,
                          default_flow_style=False)
    elif purpose == 'indexing':
        with open(config["host_url_export_file"], 'r') as f:
            data = yaml.safe_load(f)
            host = data['aoss_host']
            aoss_index_name = data['aoss_index_name']
        if host is not None and len(host) > 0:
            print(f'OpenSearch host url: {host}')
            print("Running indexing . . . . .")
            df_docs = pd.read_csv(config["data_location"])
            index_docs_opensearch(host.strip(), aoss_index_name, df_docs, text_col=config["indexing_column"])

            print('Indexing completed!')
        else:
            print(f'Indexing could not be completed!!!')
