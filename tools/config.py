
db_config = {
"db_host": "database-1.cx4aggus4yac.us-east-1.rds.amazonaws.com",
"db_port": 5432,
"db_name": "data_analyst_rdspg"
}

secret_name = "rds!db-d55f40a3-bb2d-4ec5-8660-c3f0a21629cd"
region_name = "us-east-1"


vector_db_config = {
        "host": "data-analyst-grit-postgresdb-vhuedimucp1q.cx4aggus4yac.us-east-1.rds.amazonaws.com",  # RDS endpoint address
        "port": 5432,  # RDS port number
        "database": "vectorstore",  # Database name from CloudFormation
        "user": "admin25",  # Database username from CloudFormation
        "password": "BlsAmz#20"  # Database password from CloudFormation
    }

vector_table_name = "vector_table"

fshot_example_filename = "examples.xlsx"

explnation_modelid = "anthropic.claude-3-haiku-20240307-v1:0"