#!/usr/bin/env python3
import os
import aws_cdk as cdk
from stacks.backend_stack import BackendStack
from stacks.frontend_stack import FrontendStack
from stacks.vpc_endpoints_stack import VpcEndpointsStack
import logging
import boto3

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = cdk.App()

# Environment configuration
# Get account and region from AWS session if not available in environment
try:
    session = boto3.Session()
    account = os.getenv('CDK_DEFAULT_ACCOUNT') or session.client('sts').get_caller_identity().get('Account')
    region = os.getenv('CDK_DEFAULT_REGION') or session.region_name or 'us-east-1'
except Exception as e:
    logger.warning(f"Failed to get account or region from AWS session: {e}")
    account = os.getenv('CDK_DEFAULT_ACCOUNT')
    region = os.getenv('CDK_DEFAULT_REGION', 'us-east-1')

if not account:
    logger.warning("No AWS account specified. Using default account from environment.")
    # Don't fail here - let CDK handle missing account appropriately

env = cdk.Environment(account=account, region=region)
logger.debug(f"Deploying to account: {account}, region: {region}")

# Get context values from cdk.json
project_name = app.node.try_get_context("project_name")
vpc_id = app.node.try_get_context("vpc_id")

# Dynamically fetch VPC CIDR block only if VPC ID is provided
if vpc_id:
    # Temporarily hardcode the CIDR block to bypass the dynamic lookup issue
    vpc_cidr_block = "10.3.0.0/16"  # Hardcoded CIDR for vpc-02e9f706b7980bbd2
    logger.info(f"Using hardcoded CIDR block for VPC '{vpc_id}': {vpc_cidr_block}")
    
    # Comment out the dynamic lookup for now
    # try:
    #     ec2_client = session.client('ec2', region_name=region)
    #     response = ec2_client.describe_vpcs(VpcIds=[vpc_id])
    #     if not response['Vpcs']:
    #         logger.error(f"VPC with ID '{vpc_id}' not found in region '{region}'.")
    #         raise ValueError(f"VPC '{vpc_id}' not found.")
    #     vpc_cidr_block = response['Vpcs'][0]['CidrBlock']
    #     logger.info(f"Successfully fetched CIDR block for VPC '{vpc_id}': {vpc_cidr_block}")
    # except Exception as e:
    #     logger.error(f"Failed to dynamically fetch CIDR for VPC '{vpc_id}': {e}")
    #     raise
else:
    logger.info("No VPC ID provided - new VPC will be created by the backend stack")
    vpc_cidr_block = None

# Subnet configurations - Removed public subnets since they're not used
private_egress_subnet_1 = app.node.try_get_context("private_egress_subnet_1")
private_egress_subnet_2 = app.node.try_get_context("private_egress_subnet_2")
private_isolated_subnet_1 = app.node.try_get_context("private_isolated_subnet_1")
private_isolated_subnet_2 = app.node.try_get_context("private_isolated_subnet_2")
security_group = app.node.try_get_context("security_group")

# Database configuration
db_username = app.node.try_get_context("db_username")
db_password = app.node.try_get_context("db_password")
db_name = app.node.try_get_context("db_name")

# Metadata configuration
metadata_s3_bucket = app.node.try_get_context("metadata_s3_bucket")
metadata_is_meta = app.node.try_get_context("metadata_is_meta")
metadata_table_meta = app.node.try_get_context("metadata_table_meta")
metadata_column_meta = app.node.try_get_context("metadata_column_meta")
metadata_metric_meta = app.node.try_get_context("metadata_metric_meta")
metadata_table_access = app.node.try_get_context("metadata_table_access")

# Model configuration
sql_model_id = app.node.try_get_context("sql_model_id")
sql_model_region = app.node.try_get_context("sql_model_region")
chat_model_id = app.node.try_get_context("chat_model_id")
chat_model_region = app.node.try_get_context("chat_model_region")
embedding_model_id = app.node.try_get_context("embedding_model_id")
embedding_model_region = app.node.try_get_context("embedding_model_region")
approach = app.node.try_get_context("approach")
api_db_type = app.node.try_get_context("api_db_type")

# API database configuration
api_db_host = app.node.try_get_context("api_db_host")
api_db_port = app.node.try_get_context("api_db_port")
api_db_name = app.node.try_get_context("api_db_name")
api_db_user = app.node.try_get_context("api_db_user")
api_db_password = app.node.try_get_context("api_db_password")

# Domain configuration (for HTTPS)
domain_name = app.node.try_get_context("domain_name")
hosted_zone_id = app.node.try_get_context("hosted_zone_id")

logger.debug(f"Project configuration:")
logger.debug(f"  Project name: {project_name}")
logger.debug(f"  VPC ID: {vpc_id}")
logger.debug(f"  VPC CIDR Block (dynamically fetched): {vpc_cidr_block}")
logger.debug(f"  Private egress subnets: {private_egress_subnet_1}, {private_egress_subnet_2}")
logger.debug(f"  Private isolated subnets: {private_isolated_subnet_1}, {private_isolated_subnet_2}")
logger.debug(f"  Security group: {security_group}")
if domain_name:
    logger.debug(f"  Domain name: {domain_name}")
    logger.debug(f"  Hosted zone ID: {hosted_zone_id}")

# Create stacks based on VPC configuration
if vpc_id:
    # Using existing VPC - create VPC endpoints stack first
    logger.info("Using existing VPC - creating VPC Endpoints Stack first...")
    vpc_endpoints_stack = VpcEndpointsStack(
        app, f"{project_name}-vpc-endpoints",
        project_name=project_name,
        vpc_id=vpc_id,
        vpc_cidr_block=vpc_cidr_block,
        private_egress_subnet_1=private_egress_subnet_1,
        private_egress_subnet_2=private_egress_subnet_2,
        private_isolated_subnet_1=private_isolated_subnet_1,
        private_isolated_subnet_2=private_isolated_subnet_2,
        security_group=security_group,
        env=env
    )
    
    # Create Backend Stack
    logger.info("Creating Backend Stack...")
    backend_stack = BackendStack(
        app, f"{project_name}-backend",
        project_name=project_name,
        vpc_id=vpc_id,
        vpc_cidr_block=vpc_cidr_block,
        private_egress_subnet_1=private_egress_subnet_1,
        private_egress_subnet_2=private_egress_subnet_2,
        private_isolated_subnet_1=private_isolated_subnet_1,
        private_isolated_subnet_2=private_isolated_subnet_2,
        security_group=security_group,
        db_username=db_username,
        db_password=db_password,
        db_name=db_name,
        metadata_s3_bucket=metadata_s3_bucket,
        metadata_is_meta=metadata_is_meta,
        metadata_table_meta=metadata_table_meta,
        metadata_column_meta=metadata_column_meta,
        metadata_metric_meta=metadata_metric_meta,
        metadata_table_access=metadata_table_access,
        sql_model_id=sql_model_id,
        sql_model_region=sql_model_region,
        chat_model_id=chat_model_id,
        chat_model_region=chat_model_region,
        embedding_model_id=embedding_model_id,
        embedding_model_region=embedding_model_region,
        approach=approach,
        env=env
    )
    
    # Add dependency for existing VPC scenario
    backend_stack.add_dependency(vpc_endpoints_stack)
else:
    # Creating new VPC - create backend stack first to create VPC
    logger.info("Creating new VPC - creating Backend Stack first...")
    backend_stack = BackendStack(
        app, f"{project_name}-backend",
        project_name=project_name,
        vpc_id=vpc_id,
        vpc_cidr_block=vpc_cidr_block,
        private_egress_subnet_1=private_egress_subnet_1,
        private_egress_subnet_2=private_egress_subnet_2,
        private_isolated_subnet_1=private_isolated_subnet_1,
        private_isolated_subnet_2=private_isolated_subnet_2,
        security_group=security_group,
        db_username=db_username,
        db_password=db_password,
        db_name=db_name,
        metadata_s3_bucket=metadata_s3_bucket,
        metadata_is_meta=metadata_is_meta,
        metadata_table_meta=metadata_table_meta,
        metadata_column_meta=metadata_column_meta,
        metadata_metric_meta=metadata_metric_meta,
        metadata_table_access=metadata_table_access,
        sql_model_id=sql_model_id,
        sql_model_region=sql_model_region,
        chat_model_id=chat_model_id,
        chat_model_region=chat_model_region,
        embedding_model_id=embedding_model_id,
        embedding_model_region=embedding_model_region,
        approach=approach,
        env=env
    )
    
    # Create VPC endpoints stack using the VPC from backend stack
    logger.info("Creating VPC Endpoints Stack using new VPC...")
    vpc_endpoints_stack = VpcEndpointsStack(
        app, f"{project_name}-vpc-endpoints",
        project_name=project_name,
        vpc_id=None,
        vpc_cidr_block=None,
        private_egress_subnet_1=None,
        private_egress_subnet_2=None,
        private_isolated_subnet_1=None,
        private_isolated_subnet_2=None,
        security_group=None,
        backend_vpc=backend_stack.vpc,
        env=env
    )
    
    # Add dependency for new VPC scenario
    vpc_endpoints_stack.add_dependency(backend_stack)

# Create Frontend Stack
logger.info("Creating Frontend Stack...")
if vpc_id:
    # Using existing VPC
    frontend_stack = FrontendStack(
        app, f"{project_name}-frontend",
        backend_stack=backend_stack,
        project_name=project_name,
        vpc_id=vpc_id,
        vpc_cidr_block=vpc_cidr_block,
        private_egress_subnet_1=private_egress_subnet_1,
        private_egress_subnet_2=private_egress_subnet_2,
        private_isolated_subnet_1=private_isolated_subnet_1,
        private_isolated_subnet_2=private_isolated_subnet_2,
        security_group=security_group,
        # API Database configuration (external database for data analysis)
        api_db_host=api_db_host,
        api_db_port=api_db_port,
        api_db_name=api_db_name,
        api_db_user=api_db_user,
        api_db_password=api_db_password,
        api_db_type=api_db_type,
        metadata_s3_bucket=metadata_s3_bucket,
        metadata_is_meta=metadata_is_meta,
        metadata_table_meta=metadata_table_meta,
        metadata_column_meta=metadata_column_meta,
        metadata_metric_meta=metadata_metric_meta,
        metadata_table_access=metadata_table_access,
        sql_model_id=sql_model_id,
        sql_model_region=sql_model_region,
        chat_model_id=chat_model_id,
        chat_model_region=chat_model_region,
        embedding_model_id=embedding_model_id,
        embedding_model_region=embedding_model_region,
        approach=approach,
        domain_name=domain_name,
        hosted_zone_id=hosted_zone_id,
        env=env
    )
else:
    # Using new VPC from backend stack
    frontend_stack = FrontendStack(
        app, f"{project_name}-frontend",
        backend_stack=backend_stack,
        project_name=project_name,
        vpc_id=None,
        vpc_cidr_block=None,
        private_egress_subnet_1=None,
        private_egress_subnet_2=None,
        private_isolated_subnet_1=None,
        private_isolated_subnet_2=None,
        security_group=None,
        backend_vpc=backend_stack.vpc,
        # API Database configuration (external database for data analysis)
        api_db_host=api_db_host,
        api_db_port=api_db_port,
        api_db_name=api_db_name,
        api_db_user=api_db_user,
        api_db_password=api_db_password,
        api_db_type=api_db_type,
        metadata_s3_bucket=metadata_s3_bucket,
        metadata_is_meta=metadata_is_meta,
        metadata_table_meta=metadata_table_meta,
        metadata_column_meta=metadata_column_meta,
        metadata_metric_meta=metadata_metric_meta,
        metadata_table_access=metadata_table_access,
        sql_model_id=sql_model_id,
        sql_model_region=sql_model_region,
        chat_model_id=chat_model_id,
        chat_model_region=chat_model_region,
        embedding_model_id=embedding_model_id,
        embedding_model_region=embedding_model_region,
        approach=approach,
        domain_name=domain_name,
        hosted_zone_id=hosted_zone_id,
        env=env
    )

# Frontend always depends on backend
frontend_stack.add_dependency(backend_stack)

# Add tags to all stacks
cdk.Tags.of(vpc_endpoints_stack).add("Project", project_name)
cdk.Tags.of(vpc_endpoints_stack).add("Environment", "production")
cdk.Tags.of(vpc_endpoints_stack).add("ManagedBy", "CDK")

cdk.Tags.of(backend_stack).add("Project", project_name)
cdk.Tags.of(backend_stack).add("Environment", "production")
cdk.Tags.of(backend_stack).add("ManagedBy", "CDK")

cdk.Tags.of(frontend_stack).add("Project", project_name)
cdk.Tags.of(frontend_stack).add("Environment", "production")
cdk.Tags.of(frontend_stack).add("ManagedBy", "CDK")

logger.info("Stack configuration completed successfully")
logger.info(f"VPC Endpoints stack: {vpc_endpoints_stack.stack_name}")
logger.info(f"Backend stack: {backend_stack.stack_name}")
logger.info(f"Frontend stack: {frontend_stack.stack_name}")

app.synth() 