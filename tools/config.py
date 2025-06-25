
fshot_example_filename = "examples.xlsx" ## Name of the file which contains the fewshot examples
emb_model = "cohere.embed-english-v3" ## embedding model id
explanation_modelid = "anthropic.claude-3-haiku-20240307-v1:0" ## model to generate explanations from the SQL which will be added to fewshot examples
region_name = "us-east-1"

## vector database parameters
vector_db_config = {
        "host": "<DATABASE ENDPOINT NAME>",  # RDS endpoint address
        "port": "<PORT NUMBER>",  # RDS port number
        "database": "<DATABASE NAME>",  # Database name from CloudFormation output
        "user": "<USERNAME>",  # Database username from CloudFormation output
        "password": "<PASSWORD>"  # Database password from CloudFormation output
                    }

## SQL database parameters(Set the values for the following parameters)
db_config = {
        "host": "<DATABASE ENDPOINT NAME>",
        "port": "<PORT NUMBER>",
        "user": "<USERNAME>",
        "password": "<PASSWORD>"
            }
