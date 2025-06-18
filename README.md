# Data Analyst Platform 🚀

A full-stack AWS data analysis platform with AI-powered SQL generation, featuring serverless backend processing and a secure Streamlit frontend interface.

## 🎯 Key Features

- **🤖 AI-Powered**: Bedrock integration for natural language to SQL conversion
- **⚡ Serverless Backend**: AWS Lambda functions for scalable data processing
- **📊 Streamlit Frontend**: Interactive web interface running on ECS Fargate
- **🗄️ Database**: PostgreSQL RDS for data storage and vector embeddings
- **🔐 Secure Access**: Bastion host with SSM Session Manager (no public IPs)
- **📋 Monitoring**: CloudWatch logs for all components

## 🏗️ Architecture

![Data Analyst Platform Architecture](architecture.jpg)

### Backend (Serverless)
- **data-analyst Lambda**: Main orchestrator, handles requests and responses
- **querybot Lambda**: Specialized SQL generation using few-shot learning
- **Custom Layers**: Dependencies (pandas, psycopg2, s3fs, openpyxl)
- **API Gateway**: RESTful API with API key authentication

### Frontend (Container-based)
- **Streamlit Application**: Interactive web interface on ECS Fargate
- **Internal ALB**: Application Load Balancer (private, no internet access)
- **Auto-scaling**: CPU/memory-based scaling (1-5 tasks)

### Security & Access
- **EC2 Bastion Host**: Secure access via SSM Session Manager
- **No Public IPs**: All components in private subnets
- **VPC Architecture**: Private subnets with egress and isolated subnets
- **IAM Roles**: Least privilege access for all components

## ⚡ Quick Start

### Prerequisites
- AWS CLI configured with appropriate permissions
- AWS CDK CLI installed (`npm install -g aws-cdk`)
- Docker installed
- Python 3.10+

### 1. Configure Infrastructure
Update key variables in `cdk.json`:

```json
{
  "context": {
    "project_name": "data-analyst",
    "vpc_id": "vpc-xxxxxxxxxxxxxxxxx",
    "private_egress_subnet_1": "subnet-xxxxxxxxxxxxxxxxx",
    "private_egress_subnet_2": "subnet-xxxxxxxxxxxxxxxxx", 
    "private_isolated_subnet_1": "subnet-xxxxxxxxxxxxxxxxx",
    "private_isolated_subnet_2": "subnet-xxxxxxxxxxxxxxxxx",
    "db_password": "your-secure-password",
    "api_db_host": "your-database-endpoint.region.rds.amazonaws.com",
    "api_db_type": "postgresql"
    ...
  }
}
```

### 2. Deploy
```bash
git clone <repository>
cd DataAnalyst
./deploy.sh deploy
```

### 3. Access
```bash
./ssh_tunnel.sh
# Open browser: http://localhost:8080
```

### Configuration Reference

<details>
<summary><b>Complete Configuration Options</b></summary>

**Core Infrastructure:**
- `project_name`: Base name for all AWS resources
- `vpc_id`: Existing VPC ID where resources will be deployed
- `private_egress_subnet_1/2`: Private subnets with NAT Gateway (for Lambda/ECS)
- `private_isolated_subnet_1/2`: Private isolated subnets (for RDS database)

**Database Configuration:**
- `db_username`: PostgreSQL master username (default: "postgres")
- `db_password`: PostgreSQL master password
- `db_name`: PostgreSQL database name (default: "postgres")

**External Database (for API queries):**
- `api_db_host`: External database hostname
- `api_db_port`: External database port (5432 for PostgreSQL, 5439 for Redshift)
- `api_db_name`: External database name
- `api_db_user`: External database username
- `api_db_password`: External database password
- `api_db_type`: Database type (`postgresql`, `redshift`, `s3`)

**AI Model Configuration:**
- `sql_model_id`: Bedrock model for SQL generation (default: Claude Sonnet)
- `chat_model_id`: Bedrock model for chat responses (default: Claude Haiku)
- `embedding_model_id`: Bedrock model for vector embeddings (default: Cohere)
- `approach`: AI approach method (`few_shot`, `zero_shot`)

**Metadata Configuration (for S3 databases):**
- `metadata_s3_bucket`: S3 bucket containing data and schema files
- `metadata_is_meta`: Enable metadata-driven schema discovery
- `metadata_table_meta`: S3 key for table metadata Excel file
- `metadata_column_meta`: S3 key for column metadata Excel file

</details>

## 📊 Supported Database Types

### PostgreSQL
```json
{
  "api_db_host": "your-postgres-instance.region.rds.amazonaws.com",
  "api_db_port": 5432,
  "api_db_name": "your_database",
  "api_db_user": "your_user",
  "api_db_password": "your_password",
  "api_db_type": "postgresql"
}
```

### Redshift
```json
{
  "api_db_host": "your-redshift-cluster.region.redshift.amazonaws.com",
  "api_db_port": 5439,
  "api_db_name": "your_database",
  "api_db_user": "your_user",
  "api_db_password": "your_password",
  "api_db_type": "redshift"
}
```

### S3-Athena
```json
{
  "api_db_host": "",
  "api_db_port": 0,
  "api_db_name": "your_s3_data_lake_name",
  "api_db_user": "",
  "api_db_password": "",
  "api_db_type": "s3"
}
```

**S3-Athena Flow:**
- **S3 Input**: Upload a ZIP file containing nested folders of CSV files
- **Automatic Processing**: System extracts ZIP and organizes data automatically
- **Schema Generation**: Automatically creates schema files from CSV structure
- **Athena Integration**: Uses AWS Glue Catalog for query execution

**Input ZIP Structure:**
```
your_database.zip
├── customers/
│   └── customers.csv
├── orders/
│   └── orders.csv
├── products/
│   └── products.csv
└── sales/
    ├── sales_2023.csv
    └── sales_2024.csv
```

**Upload Process:**
1. **Prepare ZIP**: Create ZIP file with folders containing CSV files
2. **Upload via UI**: Use Streamlit interface to upload ZIP file
3. **Automatic Processing**: System extracts, validates, and organizes data
4. **Schema Generation**: Automatically creates database schema from CSV headers
5. **Ready to Query**: Start asking questions about your data immediately

## 📊 Architecture Flow

### High-Level Data Flow
```
User Query → Streamlit UI → API Gateway → Data Analyst Lambda → QueryBot Lambda → Database
     ↑                                           ↓                      ↓
     └── Results ← Response Processing ← SQL Execution ← SQL Generation ←┘
```

### Detailed Processing Flow

#### 1. **User Interaction**
```
User (SSH Tunnel) → Streamlit UI (ECS) → API Gateway → Data Analyst Lambda
```
- User connects via secure SSH tunnel to bastion host
- Accesses Streamlit interface running on ECS Fargate
- Submits natural language query through web interface
- Request routed through API Gateway with authentication

#### 2. **Query Processing Pipeline**
```
Data Analyst Lambda:
├── Input Validation & Authentication
├── Cache Check (Vector Similarity Search)
│   ├── If Found: Return Cached SQL + Results
│   └── If Not Found: Continue to Generation
├── Schema Extraction (Database/S3 Metadata)
├── Question Intent Classification (SQL/Plot/Chat)
└── Route to Appropriate Handler
```

#### 3. **SQL Generation (QueryBot Lambda)**
```
QueryBot Lambda:
├── Few-Shot Learning (Vector Examples)
├── Schema Context Injection
├── Bedrock Model Invocation
├── SQL Query Generation
├── Query Validation & Optimization
└── Return Generated SQL
```

#### 4. **Execution & Response**
```
Data Analyst Lambda:
├── Execute SQL Against Target Database
│   ├── PostgreSQL/Redshift: Direct Connection
│   └── S3: Athena Query Execution
├── Process Results (DataFrame)
├── Generate Natural Language Explanation
├── Cache Successful Query-Result Pairs
└── Return Formatted Response
```

#### 5. **Caching System**
```
Vector Database (PostgreSQL + pgvector):
├── Store: Question Embeddings + SQL Queries
├── Search: Cosine Similarity for Query Matching
├── Threshold: Configurable similarity matching
└── Performance: Sub-second cache retrieval
```

### Component Interactions

#### **Data Analyst Lambda** (Main Orchestrator)
- **Input**: Natural language queries, database configurations
- **Functions**: Request validation, caching, schema extraction, response formatting
- **Outputs**: SQL results, explanations, visualizations
- **Dependencies**: QueryBot Lambda, PostgreSQL, target databases

#### **QueryBot Lambda** (SQL Generator)
- **Input**: Processed queries, schema context, few-shot examples
- **Functions**: AI-powered SQL generation using Bedrock models
- **Outputs**: Optimized SQL queries with explanations
- **Dependencies**: Bedrock (Claude/Cohere), vector database

#### **Vector Cache System**
- **Storage**: PostgreSQL with pgvector extension
- **Function**: Semantic similarity search for query caching
- **Performance**: Reduces response time from ~10s to ~2s for similar queries
- **Intelligence**: Learns from successful query patterns

#### **Database Connectivity**
- **PostgreSQL/Redshift**: Direct psycopg2 connections
- **S3/Athena**: Boto3 with Glue catalog integration
- **Schema Discovery**: Automated metadata extraction and caching
- **Security**: VPC endpoints, private subnets, encrypted connections

### Security Architecture
- **No Public IPs**: All components in private/isolated subnets
- **Bastion Access**: SSM Session Manager (no SSH keys required)
- **Network Security**: Security groups with minimal required access
- **Data Encryption**: In-transit and at-rest encryption for all data flows

## 🔧 Management Commands

### Deployment
```bash
./deploy.sh deploy           # Deploy full infrastructure
./deploy.sh redeploy         # Destroy and redeploy everything
./deploy.sh destroy          # Clean up all resources
./deploy.sh status           # Check deployment status
./deploy.sh build-layers     # Build custom Lambda layers only
./deploy.sh cleanup          # Clean build artifacts
```

### Monitoring
```bash
# View Lambda logs using the view_logs.sh script
./view_logs.sh data-analyst    # View data-analyst Lambda logs
./view_logs.sh querybot        # View querybot Lambda logs
./view_logs.sh streamlit       # View Streamlit application logs

# Or use AWS CLI directly
aws logs tail /aws/lambda/data-analyst-data-analyst --profile profile_name --follow
aws logs tail /aws/lambda/data-analyst-querybot --profile profile_name --follow
aws logs tail /data-analyst-streamlit-ui --profile profile_name --follow
```

### Access Management
```bash
# Create tunnel (includes key management)
./ssh_tunnel.sh

# Get bastion instance ID
aws cloudformation describe-stacks --stack-name data-analyst-frontend \
  --query "Stacks[0].Outputs[?OutputKey=='BastionHostInstanceId'].OutputValue" \
  --output text --profile profile_name
```

## 🗂️ Project Structure

```
DataAnalyst/
├── cdk/                          # AWS CDK Infrastructure as Code
│   ├── app.py                    # CDK app entry point
│   ├── cdk.json                  # CDK configuration
│   └── stacks/
│       ├── backend_stack.py      # Lambda functions, RDS, API Gateway
│       ├── frontend_stack.py     # ECS, ALB, Bastion host
│       └── vpc_endpoints_stack.py # VPC endpoints for AWS services
├── code/
│   ├── data-analyst/             # Main orchestrator Lambda function
│   │   ├── lambda_function.py    # Main Lambda handler
│   │   ├── scripts/
│   │   │   ├── orchestrator_db.py # Core orchestration logic
│   │   │   ├── cache_operations.py # Vector cache operations
│   │   │   ├── time_tracker.py   # Performance monitoring
│   │   │   └── query_db/         # Database query modules
│   │   │       ├── classifier.py # Query classification
│   │   │       ├── get_schema_str.py # Schema extraction
│   │   │       ├── pgsql_executor.py # SQL execution
│   │   │       └── postprocessor.py # Result processing
│   │   └── db_data/              # Sample data and schemas
│   ├── querybot/                 # SQL generation Lambda function
│   │   ├── lambda_function.py    # QueryBot Lambda handler
│   │   └── scripts/
│   │       ├── sql/              # SQL generation modules
│   │       │   ├── generator.py  # SQL query generation
│   │       │   ├── executor.py   # SQL execution helpers
│   │       │   └── evaluator.py  # Query evaluation
│   │       └── support/          # Support utilities
│   └── tools/                    # Utility handlers
├── layers/                       # Custom Lambda layers
│   ├── data-analyst-requirements.txt
│   ├── querybot-requirements.txt
│   └── create_*_layer_zip.sh     # Layer build scripts
├── streamlit/                    # Streamlit web application
│   ├── Dockerfile               # Container configuration
│   └── UI/
│       ├── Home.py              # Main Streamlit app
│       ├── config.py            # UI configuration
│       └── pages/
│           └── DataAnalyst.py   # Data analysis interface
├── notebooks/                   # Jupyter notebooks for development
├── test/                        # Test data and datasets
├── tools/                       # Development utilities
├── docs/                        # Documentation files
├── deploy.sh                    # Main deployment script
├── ssh_tunnel.sh               # Secure access tunnel script
└── view_logs.sh                # Log viewing utility
```

## 🔒 Security Features

- **No Public Access**: All resources in private subnets
- **Bastion Host**: SSM Session Manager access only (no SSH keys required)
- **EC2 Instance Connect**: Temporary SSH key injection for tunneling
- **VPC Endpoints**: Private connectivity to AWS services
- **API Keys**: Secured API Gateway access
- **IAM Roles**: Least privilege access
- **Security Groups**: Restrictive network access controls

## 🚨 Troubleshooting

### Access Issues
```bash
# Check bastion host status
aws ec2 describe-instances --instance-ids <INSTANCE-ID> --profile profile_name

# Test tunnel creation
./ssh_tunnel.sh -l 8080

# Verify ALB health
aws elbv2 describe-target-health --target-group-arn <TARGET-GROUP-ARN> --profile profile_name
```

### Application Issues
```bash
# Check ECS service status
aws ecs describe-services --cluster data-analyst-streamlit-cluster \
  --services data-analyst-streamlit --profile profile_name

# View container logs
aws logs tail /data-analyst-streamlit-ui --profile profile_name
```

### Lambda Issues
```bash
# Check Lambda function logs
aws logs tail /aws/lambda/data-analyst-data-analyst --profile profile_name

# Verify environment variables
aws lambda get-function-configuration --function-name data-analyst-data-analyst --profile profile_name
```

### Database Issues
```bash
# Verify RDS instance
aws rds describe-db-instances --db-instance-identifier data-analyst-postgres-db --profile profile_name

# Check database credentials
aws secretsmanager get-secret-value --secret-id data-analyst-db-credentials --profile profile_name
```

## 📋 Configuration

Key configuration files:
- `cdk.json`: CDK app configuration and VPC settings
- `layers/requirements.txt`: Lambda layer dependencies  
- `streamlit/`: Frontend application configuration
- Environment variables set via CDK deployment

## 💡 Usage Tips

- **First Time**: Allow ~5 minutes for ECS service to fully start
- **Tunnel**: Use `./ssh_tunnel.sh` for easiest access
- **Scaling**: ECS auto-scales based on CPU/memory usage
- **Logs**: Check CloudWatch for debugging both Lambda and ECS issues
- **Security**: No permanent SSH keys required - uses EC2 Instance Connect

## Contributors

- [Adithya Suresh](https://www.linkedin.com/in/adithyaxx/) - Deep Learning Architect, AWS Generative AI Innovation Center
- [Debasish Mishra](https://www.linkedin.com/in/debnitxl/) - Senior Data Scientist, AWS Generative AI Innovation Center
- [Milly Nguyen](https://www.linkedin.com/in/milly-nguyen/) - Associate Solutions Architect, AWS Global Sales
- [Sujoy Roy](https://www.linkedin.com/in/sujoy-roy-95523136/) - Principal Applied Scientist, AWS Generative AI Innovation Center

## License

This project is licensed under the terms of the MIT License. See the [LICENSE](./LICENSE) file for details.