import json
import logging
import time
from typing import Optional

from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    CustomResource,
    SecretValue,
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_s3 as s3,
    aws_lambda as _lambda,
    aws_apigateway as apigateway,
    aws_iam as iam,
    aws_dynamodb as dynamodb,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as sfn_tasks,
    aws_bedrock as bedrock,
    aws_athena as athena,
    aws_ssm as ssm,
    aws_logs as logs,
    aws_events as events,
    aws_events_targets as targets,
    aws_cloudformation as cfn,
    aws_apigateway as apigw,
    custom_resources as cr
)
from constructs import Construct
import aws_cdk as cdk
from . import setup_logger
import secrets
import string
import hashlib
import boto3
import urllib3

logger = logging.getLogger(__name__)

class BackendStack(Stack):
    """
    Backend stack that supports multiple database types:
    - PostgreSQL (RDS in private isolated subnets)
    - Redshift (external connection)
    - S3-Athena (S3 data lake with Athena queries)
    
    Creates infrastructure for:
    - Lambda functions for data analysis in private egress subnets
    - API Gateway for frontend communication
    - Bedrock guardrails for AI safety
    - Athena workgroup and Glue catalog for S3-Athena support
    """

    def __init__(self, scope: Construct, construct_id: str, 
                 project_name: str,
                 vpc_id: str = None,
                 vpc_cidr_block: str = None,
                 private_egress_subnet_1: str = None,
                 private_egress_subnet_2: str = None,
                 private_isolated_subnet_1: str = None,
                 private_isolated_subnet_2: str = None,
                 security_group: str = None,
                 db_username: str = "admin",
                 db_password: str = "defaultPassword123",
                 db_name: str = "vectorstore",
                 guardrail_name: str = "data-analyst-bedrock-guardrail",
                 metadata_s3_bucket: str = None,
                 metadata_is_meta: bool = True,
                 metadata_table_meta: str = "schema/tables.xlsx",
                 metadata_column_meta: str = "schema/columns.xlsx",
                 metadata_metric_meta: str = "schema/metrics.xlsx",
                 metadata_table_access: str = "",
                 sql_model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0",
                 chat_model_id: str = "anthropic.claude-3-haiku-20240307-v1:0",
                 embedding_model_id: str = "cohere.embed-multilingual-v3",
                 approach: str = "few_shot",
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.template_options.description = f"{project_name} (uksb-vhbajid3y7) (tag: Backend)"
        self.project_name = project_name
        self.metadata_s3_bucket = metadata_s3_bucket
        self.db_name = db_name
        self.db_username = db_username
        self.db_password = db_password
        
        # Store metadata configuration parameters
        self.metadata_is_meta = metadata_is_meta
        self.metadata_table_meta = metadata_table_meta
        self.metadata_column_meta = metadata_column_meta
        self.metadata_metric_meta = metadata_metric_meta
        self.metadata_table_access = metadata_table_access
        
        # Store model configuration parameters  
        self.sql_model_id = sql_model_id
        self.chat_model_id = chat_model_id
        self.embedding_model_id = embedding_model_id
        self.approach = approach
        
        logger.debug(f"Initializing BackendStack for project: {project_name}")
        if metadata_s3_bucket:
            logger.debug(f"External metadata S3 bucket: {metadata_s3_bucket}")
        logger.debug(f"Database name: {db_name}")

        # Setup VPC infrastructure based on provided parameters
        self._setup_vpc_infrastructure(
            vpc_id, vpc_cidr_block,
            private_egress_subnet_1, private_egress_subnet_2,
            private_isolated_subnet_1, private_isolated_subnet_2,
            security_group
        )

        # Create RDS PostgreSQL Database in private isolated subnets
        logger.debug("Creating RDS PostgreSQL database...")
        self.postgres_db = rds.DatabaseInstance(
            self, "PostgresDB",
            instance_identifier=f"{project_name.lower()}-postgres-db",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_17_5
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE3, 
                ec2.InstanceSize.MICRO
            ),
            credentials=rds.Credentials.from_password(
                username=self.db_username,
                password=SecretValue.unsafe_plain_text(self.db_password)
            ),
            database_name=db_name,
            allocated_storage=20,
            storage_encrypted=True,
            vpc=self.vpc,
            vpc_subnets=self.private_isolated_subnets,
            security_groups=[self.security_group],
            deletion_protection=False,
            backup_retention=Duration.days(7),
            delete_automated_backups=True,
            removal_policy=RemovalPolicy.DESTROY
        )
        logger.debug(f"PostgreSQL database created: {self.postgres_db.instance_identifier}")

        # Create RDS subnet group for database
        db_subnet_group = rds.SubnetGroup(
            self, "DatabaseSubnetGroup",
            description="Subnet group for PostgreSQL database",
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            subnet_group_name=f"{project_name}-db-subnet-group-{int(time.time())}"  # Add timestamp to avoid conflicts
        )

        # Create S3-Athena infrastructure
        self._create_athena_infrastructure()

        # Create DynamoDB table for project management
        self._create_dynamodb_table()

        # Create Lambda functions and API Gateway
        self._create_lambda_functions()
        self._create_api_gateway()
        self._create_bedrock_guardrail(guardrail_name)

        # Create Step Functions workflow (after all Lambda functions are created)
        self._create_step_functions_workflow()

        # Outputs
        CfnOutput(
            self, "VpcId",
            value=self.vpc.vpc_id,
            description="VPC ID",
            export_name=f"{project_name}-vpc-id"
        )

        CfnOutput(
            self, "VpcCidrBlock",
            value=self.vpc.vpc_cidr_block,
            description="VPC CIDR Block",
            export_name=f"{project_name}-vpc-cidr-block"
        )

        CfnOutput(
            self, "DatabaseEndpoint",
            value=self.postgres_db.instance_endpoint.hostname,
            description="RDS PostgreSQL endpoint",
            export_name=f"{project_name}-db-endpoint"
        )

        CfnOutput(
            self, "ApiEndpoint",
            value=self.api_gateway_url,
            description="API Gateway endpoint",
            export_name=f"{project_name}-api-endpoint"
        )

        CfnOutput(
            self, "DataAnalysisLambdaLogGroup",
            value=f"/aws/lambda/{self.project_name}-data-analyst",
            description="CloudWatch Log Group for Data Analysis Lambda",
            export_name=f"{project_name}-data-analyst-logs"
        )
        
        CfnOutput(
            self, "QuerybotLambdaLogGroup", 
            value=f"/aws/lambda/{self.project_name}-querybot",
            description="CloudWatch Log Group for Querybot Lambda",
            export_name=f"{project_name}-querybot-logs"
        )

        CfnOutput(
            self, "AthenaWorkgroupName",
            value=self.athena_workgroup.name,
            description="Athena Workgroup for S3-Athena queries (uses default Glue catalog)",
            export_name=f"{project_name}-athena-workgroup"
        )

        CfnOutput(
            self, "StateMachineArn",
            value=self.step_functions_state_machine.state_machine_arn,
            description="ARN of the data processing state machine",
            export_name=f"{project_name}-state-machine-arn"
        )

        CfnOutput(
            self, "UploadEndpoint",
            value=f"{self.api_gateway_url}upload",
            description="API endpoint for file uploads",
            export_name=f"{project_name}-upload-endpoint"
        )

        CfnOutput(
            self, "CompleteUploadEndpoint", 
            value=f"{self.api_gateway_url}upload/complete",
            description="API endpoint for completing uploads",
            export_name=f"{project_name}-complete-upload-endpoint"
        )

        CfnOutput(
            self, "ProjectsEndpoint",
            value=f"{self.api_gateway_url}projects", 
            description="API endpoint for listing projects",
            export_name=f"{project_name}-projects-endpoint"
        )

        CfnOutput(
            self, "ProjectsTableName",
            value=self.projects_table.table_name,
            description="DynamoDB table for project management",
            export_name=f"{project_name}-projects-table-name"
        )
        
        CfnOutput(
            self, "DataAnalystLambdaArnOutput",
            value=self.data_analyst_lambda.function_arn,
            description="Data Analyst Lambda Function ARN",
            export_name=f"{self.project_name}-data-analyst-lambda-arn"
        )
        
        CfnOutput(
            self, "QuerybotLambdaArnOutput", 
            value=self.querybot_lambda.function_arn,
            description="Querybot Lambda Function ARN",
            export_name=f"{self.project_name}-querybot-lambda-arn"
        )
        
        CfnOutput(
            self, "S3BucketNameOutput",
            value=self.application_bucket.bucket_name,
            description="S3 Bucket for application data",
            export_name=f"{self.project_name}-s3-bucket-name"
        )
        
        CfnOutput(
            self, "DatabaseEndpointOutput",
            value=self.postgres_db.instance_endpoint.hostname,
            description="PostgreSQL Database Endpoint",
            export_name=f"{self.project_name}-database-endpoint"
        )

        CfnOutput(
            self, "ApiKeyId",
            value=self.api_key.key_id,
            description="API Gateway API Key ID (use this to retrieve the actual key value via AWS SDK)",
            export_name=f"{self.project_name}-api-key-id"
        )

        CfnOutput(
            self, "ApiKeyParameterName",
            value=f"/{self.project_name}/api/key",
            description="SSM Parameter Store name containing the API Key ID",
            export_name=f"{self.project_name}-api-key-parameter"
        )

        CfnOutput(
            self, "UsagePlanId",
            value=self.usage_plan.usage_plan_id,
            description="API Gateway Usage Plan ID for rate limiting",
            export_name=f"{self.project_name}-usage-plan-id"
        )

        logger.debug(f"Backend stack created successfully for project: {self.project_name}")

    def _setup_vpc_infrastructure(self, vpc_id, vpc_cidr_block,
                                   private_egress_subnet_1, private_egress_subnet_2,
                                   private_isolated_subnet_1, private_isolated_subnet_2,
                                   security_group):
        """Setup VPC infrastructure based on provided parameters."""
        if vpc_id:
            logger.debug(f"Using existing VPC: {vpc_id}")
            
            # Check if all subnets are provided
            all_subnets_provided = all([
                private_egress_subnet_1, private_egress_subnet_2,
                private_isolated_subnet_1, private_isolated_subnet_2
            ])
            
            if all_subnets_provided:
                logger.debug("All subnets provided - importing existing infrastructure")
                logger.debug(f"  VPC CIDR Block: {vpc_cidr_block}")
                logger.debug(f"  Private Egress Subnets: {private_egress_subnet_1}, {private_egress_subnet_2}")
                logger.debug(f"  Private Isolated Subnets: {private_isolated_subnet_1}, {private_isolated_subnet_2}")
                
                # Import existing VPC
                self.vpc = ec2.Vpc.from_vpc_attributes(
                    self, "ExistingVPC", 
                    vpc_id=vpc_id,
                    vpc_cidr_block=vpc_cidr_block,
                    availability_zones=[
                        self.availability_zones[0],
                        self.availability_zones[1]
                    ],
                    private_subnet_ids=[private_egress_subnet_1, private_egress_subnet_2],
                    isolated_subnet_ids=[private_isolated_subnet_1, private_isolated_subnet_2]
                )
                
                # Import existing subnets
                self.private_egress_subnet_1 = ec2.Subnet.from_subnet_id(
                    self, "PrivateEgressSubnet1", private_egress_subnet_1
                )
                self.private_egress_subnet_2 = ec2.Subnet.from_subnet_id(
                    self, "PrivateEgressSubnet2", private_egress_subnet_2
                )
                self.private_isolated_subnet_1 = ec2.Subnet.from_subnet_id(
                    self, "PrivateIsolatedSubnet1", private_isolated_subnet_1
                )
                self.private_isolated_subnet_2 = ec2.Subnet.from_subnet_id(
                    self, "PrivateIsolatedSubnet2", private_isolated_subnet_2
                )
                
                # Create subnet selections for different purposes
                self.private_egress_subnets = ec2.SubnetSelection(
                    subnets=[self.private_egress_subnet_1, self.private_egress_subnet_2]
                )
                self.private_isolated_subnets = ec2.SubnetSelection(
                    subnets=[self.private_isolated_subnet_1, self.private_isolated_subnet_2]
                )
            else:
                logger.debug("Some subnets missing - importing VPC and using available subnets")
                
                # Import existing VPC with minimal attributes
                self.vpc = ec2.Vpc.from_lookup(
                    self, "ExistingVPC",
                    vpc_id=vpc_id
                )
                
                # Use existing subnets from the VPC instead of creating new ones
                # This avoids the complexity of creating new subnets in an existing VPC
                if private_egress_subnet_1:
                    self.private_egress_subnet_1 = ec2.Subnet.from_subnet_id(
                        self, "PrivateEgressSubnet1", private_egress_subnet_1
                    )
                else:
                    # Use the first available private subnet with egress
                    if len(self.vpc.private_subnets) > 0:
                        self.private_egress_subnet_1 = self.vpc.private_subnets[0]
                    else:
                        # Fallback to any available subnet
                        self.private_egress_subnet_1 = self.vpc.isolated_subnets[0] if self.vpc.isolated_subnets else None
                
                if private_egress_subnet_2:
                    self.private_egress_subnet_2 = ec2.Subnet.from_subnet_id(
                        self, "PrivateEgressSubnet2", private_egress_subnet_2
                    )
                else:
                    # Use the second available private subnet with egress
                    if len(self.vpc.private_subnets) > 1:
                        self.private_egress_subnet_2 = self.vpc.private_subnets[1]
                    elif len(self.vpc.isolated_subnets) > 1:
                        self.private_egress_subnet_2 = self.vpc.isolated_subnets[1]
                    else:
                        # Use the same subnet if only one is available
                        self.private_egress_subnet_2 = self.private_egress_subnet_1
                
                if private_isolated_subnet_1:
                    self.private_isolated_subnet_1 = ec2.Subnet.from_subnet_id(
                        self, "PrivateIsolatedSubnet1", private_isolated_subnet_1
                    )
                else:
                    # Use the first available isolated subnet
                    if len(self.vpc.isolated_subnets) > 0:
                        self.private_isolated_subnet_1 = self.vpc.isolated_subnets[0]
                    else:
                        # Fallback to private subnets
                        self.private_isolated_subnet_1 = self.vpc.private_subnets[0] if self.vpc.private_subnets else None
                
                if private_isolated_subnet_2:
                    self.private_isolated_subnet_2 = ec2.Subnet.from_subnet_id(
                        self, "PrivateIsolatedSubnet2", private_isolated_subnet_2
                    )
                else:
                    # Use the second available isolated subnet
                    if len(self.vpc.isolated_subnets) > 1:
                        self.private_isolated_subnet_2 = self.vpc.isolated_subnets[1]
                    elif len(self.vpc.private_subnets) > 1:
                        self.private_isolated_subnet_2 = self.vpc.private_subnets[1]
                    else:
                        # Use the same subnet if only one is available
                        self.private_isolated_subnet_2 = self.private_isolated_subnet_1
                
                # Create subnet selections using available subnets
                egress_subnets = [s for s in [self.private_egress_subnet_1, self.private_egress_subnet_2] if s is not None]
                isolated_subnets = [s for s in [self.private_isolated_subnet_1, self.private_isolated_subnet_2] if s is not None]
                
                if egress_subnets:
                    self.private_egress_subnets = ec2.SubnetSelection(subnets=egress_subnets)
                else:
                    # Fallback to using subnet type selection
                    self.private_egress_subnets = ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
                
                if isolated_subnets:
                    self.private_isolated_subnets = ec2.SubnetSelection(subnets=isolated_subnets)
                else:
                    # Fallback to using subnet type selection
                    self.private_isolated_subnets = ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED)
            
            # Import or create security group
            if security_group:
                logger.debug(f"Using existing security group: {security_group}")
                self.security_group = ec2.SecurityGroup.from_security_group_id(
                    self, "ExistingSecurityGroup", security_group
                )
            else:
                logger.debug("Creating new security group in existing VPC")
                self.security_group = ec2.SecurityGroup(
                    self, "BackendSecurityGroup",
                    vpc=self.vpc,
                    description=f"Security group for {self.project_name} backend resources",
                    allow_all_outbound=True
                )
                self._add_security_group_rules()
        else:
            logger.debug("No VPC provided - creating new VPC with all required infrastructure")
            
            # Create new VPC with proper subnet configuration
            # Each AZ will have: 1 public subnet (for NAT), 1 egress subnet, 1 isolated subnet
            self.vpc = ec2.Vpc(
                self, "NewVPC",
                max_azs=2,
                nat_gateways=1,  # Need NAT Gateway for egress subnets
                ip_addresses=ec2.IpAddresses.cidr("10.1.0.0/16"),  # Use different CIDR to avoid conflicts
                subnet_configuration=[
                    ec2.SubnetConfiguration(
                        cidr_mask=24,
                        name="public",
                        subnet_type=ec2.SubnetType.PUBLIC  # Public subnets for NAT Gateway
                    ),
                    ec2.SubnetConfiguration(
                        cidr_mask=24,
                        name="private-egress",
                        subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS  # Egress subnets for Lambda functions
                    ),
                    ec2.SubnetConfiguration(
                        cidr_mask=24,
                        name="private-isolated",
                        subnet_type=ec2.SubnetType.PRIVATE_ISOLATED  # Isolated subnets for databases
                    )
                ]
            )
            
            # Create subnet selections for different purposes
            # Lambda functions will use egress subnets (can reach internet via NAT)
            self.private_egress_subnets = ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            )
            # Databases will use isolated subnets (no internet access, VPC endpoints only)
            self.private_isolated_subnets = ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            )
            
            # Create security group
            self.security_group = ec2.SecurityGroup(
                self, "BackendSecurityGroup",
                vpc=self.vpc,
                description=f"Security group for {self.project_name} backend resources",
                allow_all_outbound=True
            )
            self._add_security_group_rules()

        # Create S3 Bucket for application storage
        logger.debug("Creating S3 bucket for application storage...")
        self.application_bucket = s3.Bucket(
            self, "ApplicationBucket",
            bucket_name=f"{self.project_name.lower()}-application-bucket-{self.account}-{self.region}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED
        )
        logger.debug(f"S3 bucket created: {self.application_bucket.bucket_name}")

    def _add_security_group_rules(self):
        """Add standard security group rules for the backend resources."""
        # Add ingress rules for database access
        self.security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(5432),
            description="PostgreSQL access from VPC"
        )
        
        # Add Redshift port for external Redshift database access
        self.security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(5439),
            description="Redshift access from VPC"
        )
        
        # Add HTTPS ingress for API Gateway
        self.security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(443),
            description="HTTPS access from VPC"
        )

    def _get_next_available_cidr(self, vpc, cidr_mask, offset):
        """Get the next available CIDR block for subnet creation."""
        # This is a simplified implementation
        # In a real scenario, you'd want to check existing subnets and find available CIDR blocks
        import ipaddress
        
        vpc_network = ipaddress.IPv4Network(vpc.vpc_cidr_block)
        subnets = list(vpc_network.subnets(new_prefix=cidr_mask))
        
        # Return the first available subnet (simplified logic)
        # In production, you'd want to check against existing subnets
        return str(subnets[offset])

    def _create_athena_infrastructure(self):
        """Create Athena infrastructure for S3-Athena support.
        
        Note: We don't need to create explicit Glue resources because:
        - Athena automatically uses the Glue Data Catalog as its metastore
        - When tables are created via Athena DDL, they get automatically registered in Glue
        - This matches the approach used in the original CloudFormation template
        """
        logger.debug("Creating Athena infrastructure for S3-Athena support...")

        # Create Athena Workgroup (this is the main infrastructure needed)
        self.athena_workgroup = athena.CfnWorkGroup(
            self, "AthenaWorkgroup",
            name=f"{self.project_name}-workgroup",
            description=f"Athena workgroup for {self.project_name} S3-Athena queries",
            state="ENABLED",
            work_group_configuration=athena.CfnWorkGroup.WorkGroupConfigurationProperty(
                result_configuration=athena.CfnWorkGroup.ResultConfigurationProperty(
                    output_location=f"s3://{self.application_bucket.bucket_name}/athena-results/"
                ),
                enforce_work_group_configuration=True,
                bytes_scanned_cutoff_per_query=100000000,  # 100MB limit per query
                engine_version=athena.CfnWorkGroup.EngineVersionProperty(
                    selected_engine_version="Athena engine version 3"
                )
            )
        )

        # Note: No explicit Glue database needed - Athena will create databases/tables 
        # in the default Glue catalog automatically via DDL commands
        
        logger.debug("Athena infrastructure created successfully")

    def _create_dynamodb_table(self):
        """Create DynamoDB table for project management."""
        logger.debug("Creating DynamoDB table for project management...")
        
        self.projects_table = dynamodb.Table(
            self, "ProjectsTable",
            table_name=f"{self.project_name}-projects",
            partition_key=dynamodb.Attribute(
                name="PK",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="SK",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.DESTROY
        )
        
        logger.debug("DynamoDB table created successfully")

    def _create_lambda_functions(self):
        """Create Lambda functions for the backend services."""
        logger.debug("Creating Lambda functions...")
        
        # Create Lambda execution role with basic permissions
        lambda_role = iam.Role(
            self, "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaVPCAccessExecutionRole"),
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonBedrockFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3FullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonDynamoDBFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonAthenaFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSStepFunctionsFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSGlueConsoleFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSLambda_FullAccess")
            ]
        )

        # Use database credentials from constructor parameters
        postgres_username = self.db_username
        postgres_password = self.db_password
        
        # Create database configuration dictionary
        db_config_dict = {
            "type": "postgresql",
            "host": self.postgres_db.instance_endpoint.hostname,
            "port": self.postgres_db.instance_endpoint.port,
            "user": postgres_username,  # Use actual username from secret
            "password": postgres_password,
            "database": self.db_name
        }
        
        # Create metadata configuration dictionary (with defaults)
        metadata_config = {
            "s3_bucket_name": self.metadata_s3_bucket,
            "is_meta": self.metadata_is_meta,
            "table_meta": self.metadata_table_meta,
            "column_meta": self.metadata_column_meta,
            "metric_meta": self.metadata_metric_meta,
            "table_access": self.metadata_table_access
        }
        
        # Create metadata dictionary for model configurations (with defaults)
        metadata_dict = {
            "sql_model_id": self.sql_model_id,
            "chat_model_id": self.chat_model_id,
            "embedding_model_id": self.embedding_model_id,
            "approach": self.approach
        }
        
        # Create custom layers
        # Data Analyst custom layer
        data_analyst_dependencies_layer = _lambda.LayerVersion(
            self, "DataAnalystDependenciesLayer",
            layer_version_name=f"{self.project_name}-data-analyst-dependencies",
            description="Custom data-analyst layer for Lambda functions",
            code=_lambda.Code.from_asset("../layers/data-analyst-custom-layer.zip"),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_10],
            compatible_architectures=[_lambda.Architecture.X86_64]
        )

        # Querybot custom layer
        querybot_dependencies_layer = _lambda.LayerVersion(
            self, "QuerybotDependenciesLayer",
            layer_version_name=f"{self.project_name}-querybot-dependencies",
            description="Custom querybot layer for Lambda functions",
            code=_lambda.Code.from_asset("../layers/querybot-custom-layer.zip"),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_10],
            compatible_architectures=[_lambda.Architecture.X86_64]
        )

        # Create querybot Lambda function first (since data-analyst function references it)
        self.querybot_lambda = _lambda.Function(
            self, "QuerybotLambda",
            runtime=_lambda.Runtime.PYTHON_3_10,
            handler="lambda_function.lambda_handler",
            code=_lambda.Code.from_asset("../code/querybot"),
            timeout=Duration.minutes(10),
            memory_size=2048,
            role=lambda_role,
            function_name=f"{self.project_name}-querybot",
            layers=[querybot_dependencies_layer],
            vpc=self.vpc,
            vpc_subnets=self.private_egress_subnets,  # Deploy in egress subnets
            security_groups=[self.security_group],
            environment={
                "ACTIVE_DB_CONFIG": json.dumps(db_config_dict),
                "METADATA_CONFIG": json.dumps(metadata_config),
                "SQL_MODEL_ID": metadata_dict["sql_model_id"],
                "CHAT_MODEL_ID": metadata_dict["chat_model_id"],
                "EMBEDDING_MODEL_ID": metadata_dict["embedding_model_id"],
                "APPROACH": metadata_dict["approach"],
                "S3_BUCKET_NAME": self.application_bucket.bucket_name,
                "PROJECT_NAME": self.project_name,
                "POSTGRES_USER": self.postgres_db.instance_endpoint.hostname,
                "POSTGRES_ENDPOINT": self.postgres_db.instance_endpoint.hostname,
                "POSTGRES_USERNAME": postgres_username,
                "POSTGRES_PASSWORD": postgres_password,
                "POSTGRES_PORT": str(self.postgres_db.instance_endpoint.port),
                "POSTGRES_DB": self.db_name,
                # S3-Athena specific environment variables
                "ATHENA_WORKGROUP": self.athena_workgroup.name
            }
        )

        # Main Lambda function for data analysis
        self.data_analyst_lambda = _lambda.Function(
            self, "DataAnalystLambda",
            runtime=_lambda.Runtime.PYTHON_3_10,
            handler="lambda_function.lambda_handler",
            code=_lambda.Code.from_asset("../code/data-analyst"),
            timeout=Duration.minutes(10),
            memory_size=2048,
            role=lambda_role,
            function_name=f"{self.project_name}-data-analyst",
            layers=[data_analyst_dependencies_layer],
            vpc=self.vpc,
            vpc_subnets=self.private_egress_subnets,  # Deploy in egress subnets
            security_groups=[self.security_group],
            environment={
                "ACTIVE_DB_CONFIG": json.dumps(db_config_dict),
                "METADATA_CONFIG": json.dumps(metadata_config),
                "SQL_MODEL_ID": metadata_dict["sql_model_id"],
                "CHAT_MODEL_ID": metadata_dict["chat_model_id"],
                "EMBEDDING_MODEL_ID": metadata_dict["embedding_model_id"],
                "APPROACH": metadata_dict["approach"],
                "S3_BUCKET_NAME": self.application_bucket.bucket_name,
                "PROJECT_NAME": self.project_name,
                "POSTGRES_USER": self.postgres_db.instance_endpoint.hostname,
                "POSTGRES_ENDPOINT": self.postgres_db.instance_endpoint.hostname,
                "POSTGRES_USERNAME": postgres_username,
                "POSTGRES_PASSWORD": postgres_password,
                "POSTGRES_PORT": str(self.postgres_db.instance_endpoint.port),
                "POSTGRES_DB": self.db_name,
                "QUERYBOT_LAMBDA_NAME": f"{self.project_name}-querybot",  # Use name instead of ARN to avoid circular dependency
                # S3-Athena specific environment variables
                "ATHENA_WORKGROUP": self.athena_workgroup.name
            }
        )

        # Grant Lambda functions access to the database secret (only if secret exists)
        if self.postgres_db.secret:
            self.postgres_db.secret.grant_read(lambda_role)
        
        # Grant Lambda functions access to S3 bucket
        self.application_bucket.grant_read_write(self.data_analyst_lambda)
        self.application_bucket.grant_read_write(self.querybot_lambda)

        # Grant Lambda functions access to external metadata S3 bucket if provided
        if self.metadata_s3_bucket:
            logger.debug(f"Granting access to external metadata S3 bucket: {self.metadata_s3_bucket}")
            # Import the external bucket and grant read access
            external_metadata_bucket = s3.Bucket.from_bucket_name(
                self, "ExternalMetadataBucket",
                bucket_name=self.metadata_s3_bucket
            )
            external_metadata_bucket.grant_read(self.data_analyst_lambda)
            external_metadata_bucket.grant_read(self.querybot_lambda)
            logger.debug("External metadata S3 bucket access granted successfully")

        # Grant Lambda functions access to Athena Workgroup
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "athena:GetWorkGroup",
                    "athena:StartQueryExecution",
                    "athena:StopQueryExecution",
                    "athena:GetQueryExecution",
                    "athena:GetQueryResults",
                    "athena:BatchGetQueryExecution"
                ],
                resources=[
                    f"arn:aws:athena:{self.region}:{self.account}:workgroup/{self.athena_workgroup.name}"
                ]
            )
        )

        # Grant Lambda functions basic Glue permissions (for Athena's automatic Glue catalog integration)
        # Note: More specific than explicit Glue database creation - matches CFN template approach
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "glue:GetDatabase",
                    "glue:GetDatabases", 
                    "glue:CreateDatabase",
                    "glue:GetTable",
                    "glue:GetTables",
                    "glue:CreateTable",
                    "glue:UpdateTable",
                    "glue:DeleteTable"
                ],
                resources=["*"]  # Matches CFN template approach
            )
        )

        # Grant Lambda functions access to Step Functions
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "states:StartExecution",
                    "states:DescribeExecution",
                    "states:ListExecutions"
                ],
                resources=["*"]  # Will be restricted after Step Functions creation
            )
        )

        # Create additional Lambda functions for data processing workflow

        # UnzipFunction
        self.unzip_lambda = _lambda.Function(
            self, "UnzipLambda",
            runtime=_lambda.Runtime.PYTHON_3_10,
            handler="unzip_handler.lambda_handler",
            code=_lambda.Code.from_asset("../code/tools"),
            timeout=Duration.minutes(10),
            memory_size=2048,
            role=lambda_role,
            function_name=f"{self.project_name}-unzip",
            vpc=self.vpc,
            vpc_subnets=self.private_egress_subnets,  # Deploy in egress subnets
            security_groups=[self.security_group],
            environment={
                "S3_BUCKET_NAME": self.application_bucket.bucket_name,  # Destination bucket
                "SOURCE_BUCKET_NAME": self.metadata_s3_bucket,  # Source bucket for ZIP files
                "PROJECT_NAME": self.project_name
            }
        )

        # ProcessDataFunction
        self.process_data_lambda = _lambda.Function(
            self, "ProcessDataLambda",
            runtime=_lambda.Runtime.PYTHON_3_10,
            handler="process_data_handler.lambda_handler",
            code=_lambda.Code.from_asset("../code/tools"),
            timeout=Duration.minutes(10),
            memory_size=2048,
            role=lambda_role,
            function_name=f"{self.project_name}-process-data",
            layers=[querybot_dependencies_layer],
            vpc=self.vpc,
            vpc_subnets=self.private_egress_subnets,  # Deploy in egress subnets
            security_groups=[self.security_group],
            environment={
                "S3_BUCKET_NAME": self.application_bucket.bucket_name,
                "PROJECT_NAME": self.project_name,
                "GUARDRAIL_ID": "placeholder",  # Will be updated after guardrail creation
                "GUARDRAIL_VERSION": "placeholder"
            }
        )

        # UploadFunction
        self.upload_lambda = _lambda.Function(
            self, "UploadLambda",
            runtime=_lambda.Runtime.PYTHON_3_10,
            handler="upload_handler.lambda_handler",
            code=_lambda.Code.from_asset("../code/tools"),
            timeout=Duration.minutes(10),
            memory_size=2048,
            role=lambda_role,
            function_name=f"{self.project_name}-upload",
            vpc=self.vpc,
            vpc_subnets=self.private_egress_subnets,  # Deploy in egress subnets
            security_groups=[self.security_group],
            environment={
                "S3_BUCKET_NAME": self.application_bucket.bucket_name,
                "TABLE_NAME": self.projects_table.table_name,
                "PROJECT_NAME": self.project_name
            }
        )

        # CompleteUploadFunction
        self.complete_upload_lambda = _lambda.Function(
            self, "CompleteUploadLambda",
            runtime=_lambda.Runtime.PYTHON_3_10,
            handler="complete_upload_handler.lambda_handler",
            code=_lambda.Code.from_asset("../code/tools"),
            timeout=Duration.seconds(30),
            memory_size=256,
            role=lambda_role,
            function_name=f"{self.project_name}-complete-upload",
            vpc=self.vpc,
            vpc_subnets=self.private_egress_subnets,  # Deploy in egress subnets
            security_groups=[self.security_group],
            environment={
                "S3_BUCKET_NAME": self.application_bucket.bucket_name,
                "TABLE_NAME": self.projects_table.table_name,
                "PROJECT_NAME": self.project_name
            }
        )

        # ListProjectsFunction
        self.list_projects_lambda = _lambda.Function(
            self, "ListProjectsLambda",
            runtime=_lambda.Runtime.PYTHON_3_10,
            handler="list_projects_handler.lambda_handler",
            code=_lambda.Code.from_asset("../code/tools"),
            timeout=Duration.seconds(30),
            memory_size=256,
            role=lambda_role,
            function_name=f"{self.project_name}-list-projects",
            vpc=self.vpc,
            vpc_subnets=self.private_egress_subnets,  # Deploy in egress subnets
            security_groups=[self.security_group],
            environment={
                "TABLE_NAME": self.projects_table.table_name,
                "PROJECT_NAME": self.project_name
            }
        )

        # Removed grant statements to break circular dependencies:
        # self.projects_table.grant_read_write_data(self.upload_lambda)
        # self.projects_table.grant_read_write_data(self.complete_upload_lambda) 
        # self.projects_table.grant_read_data(self.list_projects_lambda)
        # self.application_bucket.grant_read_write(self.unzip_lambda)
        # self.application_bucket.grant_read_write(self.process_data_lambda)
        # self.application_bucket.grant_read_write(self.upload_lambda)
        # self.application_bucket.grant_read_write(self.complete_upload_lambda)
        
        # Note: DynamoDB and S3 access is provided through managed policies:
        # - AmazonDynamoDBFullAccess
        # - AmazonS3FullAccess

        logger.debug("Lambda functions created successfully")

    def _create_api_gateway(self):
        """Create API Gateway for frontend communication."""
        logger.debug("Creating API Gateway...")
        
        # Create CloudWatch log group for API Gateway
        api_log_group = logs.LogGroup(
            self, "ApiGatewayLogGroup",
            log_group_name=f"/{self.project_name}-api-gateway",
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_WEEK
        )
        
        # Create CloudWatch Logs role for API Gateway
        api_gateway_cloudwatch_role = iam.Role(
            self, "ApiGatewayCloudWatchRole",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonAPIGatewayPushToCloudWatchLogs")
            ]
        )
        
        # Create a simple REST API with CloudWatch role
        self.api_gateway = apigateway.RestApi(
            self, "DataAnalysisApi",
            rest_api_name=f"{self.project_name}-api",
            description=f"API for {self.project_name} data analysis",
            endpoint_types=[apigateway.EndpointType.REGIONAL],
            cloud_watch_role=True,  # Enable CloudWatch role management
            deploy=False  # Disable automatic deployment
        )
        
        # Set the CloudWatch role at the account level using CfnAccount
        # This will only set it if not already set
        apigateway.CfnAccount(
            self, "ApiGatewayAccount",
            cloud_watch_role_arn=api_gateway_cloudwatch_role.role_arn
        )
        
        # Enable CORS manually - Remove CorsOptions object and use direct parameters
        
        # Add CORS to root resource
        self.api_gateway.root.add_cors_preflight(
            allow_origins=["*"],
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-Api-Key"]
        )
        
        # Create API Key for authentication
        self.api_key = apigateway.ApiKey(
            self, "DataAnalysisApiKey",
            api_key_name=f"{self.project_name}-api-key",
            description=f"API Key for {self.project_name} data analysis platform",
            enabled=True
        )
        
        # Create Usage Plan
        self.usage_plan = apigateway.UsagePlan(
            self, "DataAnalysisUsagePlan",
            name=f"{self.project_name}-usage-plan",
            description=f"Usage plan for {self.project_name} API",
            throttle=apigateway.ThrottleSettings(
                rate_limit=100,  # requests per second
                burst_limit=200  # burst capacity
            ),
            quota=apigateway.QuotaSettings(
                limit=10000,  # requests per day
                period=apigateway.Period.DAY
            )
        )
        
        # Create Lambda integrations for the main endpoints
        
        # 1. Main data analysis endpoint (root POST)
        data_analyst_integration = apigateway.LambdaIntegration(
            self.data_analyst_lambda,
            request_templates={"application/json": '{"statusCode": "200"}'}
        )
        
        # Add POST method to root resource for main data analysis
        self.api_gateway.root.add_method(
            "POST", 
            data_analyst_integration,
            api_key_required=True  # Require API key
        )
        
        # 2. Upload endpoint
        upload_resource = self.api_gateway.root.add_resource("upload")
        upload_resource.add_cors_preflight(
            allow_origins=["*"],
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-Api-Key"]
        )
        
        upload_integration = apigateway.LambdaIntegration(
            self.upload_lambda,
            request_templates={"application/json": '{"statusCode": "200"}'}
        )
        
        upload_resource.add_method(
            "POST", 
            upload_integration,
            api_key_required=True  # Require API key
        )
        
        # 3. Complete upload endpoint
        complete_upload_resource = upload_resource.add_resource("complete")
        complete_upload_resource.add_cors_preflight(
            allow_origins=["*"],
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-Api-Key"]
        )
        
        complete_upload_integration = apigateway.LambdaIntegration(
            self.complete_upload_lambda,
            request_templates={"application/json": '{"statusCode": "200"}'}
        )
        
        complete_upload_resource.add_method(
            "POST", 
            complete_upload_integration,
            api_key_required=True  # Require API key
        )
        
        # 4. Projects endpoint
        projects_resource = self.api_gateway.root.add_resource("projects")
        projects_resource.add_cors_preflight(
            allow_origins=["*"],
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-Api-Key"]
        )
        
        list_projects_integration = apigateway.LambdaIntegration(
            self.list_projects_lambda,
            request_templates={"application/json": '{"statusCode": "200"}'}
        )
        
        projects_resource.add_method(
            "GET", 
            list_projects_integration,
            api_key_required=True  # Require API key
        )
        
        # Grant API Gateway permission to invoke Lambda functions
        self.data_analyst_lambda.add_permission(
            "AllowAPIGatewayInvoke",
            principal=iam.ServicePrincipal("apigateway.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_arn=f"arn:aws:execute-api:{self.region}:{self.account}:{self.api_gateway.rest_api_id}/*/*"
        )
        
        self.upload_lambda.add_permission(
            "AllowAPIGatewayInvoke",
            principal=iam.ServicePrincipal("apigateway.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_arn=f"arn:aws:execute-api:{self.region}:{self.account}:{self.api_gateway.rest_api_id}/*/*"
        )
        
        self.complete_upload_lambda.add_permission(
            "AllowAPIGatewayInvoke",
            principal=iam.ServicePrincipal("apigateway.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_arn=f"arn:aws:execute-api:{self.region}:{self.account}:{self.api_gateway.rest_api_id}/*/*"
        )
        
        self.list_projects_lambda.add_permission(
            "AllowAPIGatewayInvoke",
            principal=iam.ServicePrincipal("apigateway.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_arn=f"arn:aws:execute-api:{self.region}:{self.account}:{self.api_gateway.rest_api_id}/*/*"
        )
        
        # Store API Gateway URL for outputs  
        self.api_gateway_url = f"https://{self.api_gateway.rest_api_id}.execute-api.{self.region}.amazonaws.com/prod/"
        
        # Manual deployment
        deployment = apigateway.Deployment(
            self, "ApiDeployment",
            api=self.api_gateway,
            description=f"Deployment for {self.project_name} API"
        )
        
        # Add dependency to ensure all methods are created before deployment
        deployment.node.add_dependency(self.api_gateway.root)
        
        # Create stage manually
        self.api_stage = apigateway.Stage(
            self, "ApiStage",
            deployment=deployment,
            stage_name="prod",
            throttling_rate_limit=100,
            throttling_burst_limit=50,
            tracing_enabled=True,
            data_trace_enabled=True,
            logging_level=apigateway.MethodLoggingLevel.INFO,
            metrics_enabled=True
        )
        
        # Associate the API key with the usage plan AFTER the stage is created
        self.usage_plan.add_api_stage(
            api=self.api_gateway,
            stage=self.api_stage
        )
        
        # Associate the API key with the usage plan
        self.usage_plan.add_api_key(self.api_key)
        
        # Create SSM parameter for API endpoint
        ssm.StringParameter(
            self, "ApiEndpointParameter",
            parameter_name=f"/{self.project_name}/api/endpoint",
            string_value=self.api_gateway_url,
            description=f"API Gateway endpoint URL for {self.project_name}"
        )
        
        # Create SSM parameter for API key value (secure)
        self.api_key_parameter = ssm.StringParameter(
            self, "ApiKeyParameter", 
            parameter_name=f"/{self.project_name}/api/key",
            string_value=self.api_key.key_id,  # Store the actual API key ID
            description=f"API Key ID for {self.project_name}"
        )
        
        # Create additional SSM parameter for API key value (for applications that need the actual value)
        # Note: The actual API key value is not directly accessible via CDK, so we store the key ID
        # The application will need to use AWS SDK to get the actual key value using the key ID
        ssm.StringParameter(
            self, "ApiKeyIdParameter",
            parameter_name=f"/{self.project_name}/api-key-id",
            string_value=self.api_key.key_id,
            description=f"API Key ID for {self.project_name} - use AWS SDK to get actual key value"
        )
        
        logger.debug("API Gateway created successfully with API Key authentication")

    def _create_bedrock_guardrail(self, guardrail_name):
        """Create Bedrock guardrail for AI safety."""
        logger.debug("Creating Bedrock guardrail...")
        
        try:
            self.bedrock_guardrail = bedrock.CfnGuardrail(
                self, "BedrockGuardrail",
                name=guardrail_name,
                description=f"Guardrail for {self.project_name} to ensure safe AI interactions",
                blocked_input_messaging="This input is not allowed by our content policy.",
                blocked_outputs_messaging="This output is not allowed by our content policy.",
                content_policy_config=bedrock.CfnGuardrail.ContentPolicyConfigProperty(
                    filters_config=[
                        bedrock.CfnGuardrail.ContentFilterConfigProperty(
                            input_strength="HIGH",
                            output_strength="HIGH",
                            type="HATE"
                        ),
                        bedrock.CfnGuardrail.ContentFilterConfigProperty(
                            input_strength="HIGH",
                            output_strength="HIGH",
                            type="VIOLENCE"
                        ),
                        bedrock.CfnGuardrail.ContentFilterConfigProperty(
                            input_strength="HIGH",
                            output_strength="HIGH",
                            type="SEXUAL"
                        ),
                        bedrock.CfnGuardrail.ContentFilterConfigProperty(
                            input_strength="HIGH",
                            output_strength="HIGH",
                            type="MISCONDUCT"
                        )
                    ]
                )
            )
            
            # Update data-analyst Lambda function environment variables with guardrail info
            self.data_analyst_lambda.add_environment("GUARDRAIL_ID", self.bedrock_guardrail.attr_guardrail_id)
            self.data_analyst_lambda.add_environment("GUARDRAIL_VERSION", self.bedrock_guardrail.attr_version)
            
            # Update process-data Lambda function environment variables with guardrail info
            self.process_data_lambda.add_environment("GUARDRAIL_ID", self.bedrock_guardrail.attr_guardrail_id)
            self.process_data_lambda.add_environment("GUARDRAIL_VERSION", self.bedrock_guardrail.attr_version)
            
            logger.debug("Bedrock guardrail created successfully")
        except Exception as e:
            logger.warning(f"Failed to create Bedrock guardrail: {e}") 

    def _create_step_functions_workflow(self):
        """Create Step Functions workflow for data processing."""
        logger.debug("Creating Step Functions workflow...")
        
        # Create Step Functions log group
        self.step_functions_log_group = logs.LogGroup(
            self, "StepFunctionsLogGroup",
            log_group_name=f"/aws/states/{self.project_name}-data-processing",
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_WEEK
        )
        
        # Create the Step Functions state machine definition
        unzip_task = sfn_tasks.LambdaInvoke(
            self, "UnzipFile",
            lambda_function=self.unzip_lambda,
            output_path="$.Payload"
        )
        
        process_data_task = sfn_tasks.LambdaInvoke(
            self, "ProcessData", 
            lambda_function=self.process_data_lambda,
            output_path="$.Payload"
        )
        
        # Create the workflow definition
        definition = unzip_task.next(process_data_task)
        
        # Create Step Functions state machine
        self.step_functions_state_machine = sfn.StateMachine(
            self, "DataProcessingStateMachine",
            state_machine_name=f"{self.project_name}-data-processing",
            definition=definition,
            logs=sfn.LogOptions(
                destination=self.step_functions_log_group,
                level=sfn.LogLevel.ALL,
                include_execution_data=True
            ),
            tracing_enabled=True
        )
        
        # Note: Lambda invoke permissions are handled by AWSLambda_FullAccess and
        # Step Functions permissions are handled by AWSStepFunctionsFullAccess managed policies
        
        # Add Step Functions ARN to complete_upload_lambda environment after creation
        self.complete_upload_lambda.add_environment("DATA_PROCESSING_WORKFLOW_ARN", self.step_functions_state_machine.state_machine_arn)
        
        # Create a Custom Resource to bootstrap initial database tables
        self._create_bootstrap_trigger()
        
        logger.debug("Step Functions workflow created successfully") 

    def _create_bootstrap_trigger(self):
        """Create a CustomResource to bootstrap initial database tables during deployment."""
        logger.debug("Creating bootstrap trigger for initial table setup...")
        
        # Create a Lambda function to trigger the Step Functions workflow
        bootstrap_lambda = _lambda.Function(
            self, "BootstrapLambda",
            runtime=_lambda.Runtime.PYTHON_3_10,
            handler="index.handler",
            code=_lambda.Code.from_inline(f"""
import json
import boto3
import urllib3
import time

def send_response(event, context, response_status, response_data=None):
    \"\"\"Send response to CloudFormation custom resource\"\"\"
    if response_data is None:
        response_data = {{}}
    
    response_url = event['ResponseURL']
    response_body = {{
        'Status': response_status,
        'Reason': f'See CloudWatch Log Stream: {{context.log_stream_name}}',
        'PhysicalResourceId': context.log_stream_name,
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId'],
        'Data': response_data
    }}
    
    json_response_body = json.dumps(response_body)
    headers = {{
        'content-type': '',
        'content-length': str(len(json_response_body))
    }}
    
    try:
        http = urllib3.PoolManager()
        response = http.request('PUT', response_url, body=json_response_body, headers=headers)
        print(f"Status code: {{response.status}}")
    except Exception as e:
        print(f"Failed to send response: {{e}}")

def handler(event, context):
    try:
        print(f"Event: {{json.dumps(event)}}")
        
        if event['RequestType'] == 'Create':
            s3_client = boto3.client('s3')
            sfn_client = boto3.client('stepfunctions')
            
            bucket_name = '{self.metadata_s3_bucket}'
            
            # List all objects in the bucket to find zip files
            try:
                response = s3_client.list_objects_v2(Bucket=bucket_name)
                zip_files = []
                
                if 'Contents' in response:
                    for obj in response['Contents']:
                        if obj['Key'].endswith('.zip'):
                            zip_files.append(obj['Key'])
                
                print(f"Found {{len(zip_files)}} zip files: {{zip_files}}")
                
                if zip_files:
                    # Process the first zip file found
                    zip_file = zip_files[0]
                    project_id = zip_file.replace('.zip', '').replace('/', '_')
                    
                    execution_response = sfn_client.start_execution(
                        stateMachineArn='{self.step_functions_state_machine.state_machine_arn}',
                        name=f'bootstrap-setup-{{int(time.time())}}',
                        input=json.dumps({{
                            'projectId': project_id,
                            'dataPath': zip_file
                        }})
                    )
                    
                    print(f"Started Step Functions execution for {{zip_file}}: {{execution_response['executionArn']}}")
                    send_response(event, context, 'SUCCESS', {{
                        'ExecutionArn': execution_response['executionArn'],
                        'ProcessedFile': zip_file,
                        'ProjectId': project_id
                    }})
                else:
                    print("No zip files found in bucket. Bootstrap completed without processing.")
                    send_response(event, context, 'SUCCESS', {{
                        'Message': 'No zip files found to process',
                        'ZipFilesFound': 0
                    }})
                    
            except Exception as s3_error:
                print(f"Error listing S3 objects: {{str(s3_error)}}")
                # If we can't list objects, still succeed but log the issue
                send_response(event, context, 'SUCCESS', {{
                    'Message': f'Could not list S3 objects: {{str(s3_error)}}',
                    'ZipFilesFound': 0
                }})
        else:
            print("Non-create request, sending success response")
            send_response(event, context, 'SUCCESS')
            
    except Exception as e:
        print(f"Error: {{str(e)}}")
        send_response(event, context, 'FAILED')
        raise e
"""),
            timeout=Duration.seconds(30),
            memory_size=256,
            vpc=self.vpc,
            vpc_subnets=self.private_egress_subnets,  # Deploy in egress subnets
            security_groups=[self.security_group]
        )
        
        # Grant the bootstrap Lambda permission to start Step Functions executions
        bootstrap_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=[self.step_functions_state_machine.state_machine_arn]
            )
        )
        
        # Grant the bootstrap Lambda permission to list S3 objects
        bootstrap_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:ListBucket", "s3:GetObject"],
                resources=[
                    self.application_bucket.bucket_arn,
                    f"{self.application_bucket.bucket_arn}/*"
                ]
            )
        )
        
        # Grant access to metadata S3 bucket if provided
        if self.metadata_s3_bucket:
            bootstrap_lambda.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["s3:ListBucket", "s3:GetObject"],
                    resources=[
                        f"arn:aws:s3:::{self.metadata_s3_bucket}",
                        f"arn:aws:s3:::{self.metadata_s3_bucket}/*"
                    ]
                )
            )
        
        # Create the CustomResource that triggers the bootstrap
        CustomResource(
            self, "BootstrapTrigger",
            service_token=bootstrap_lambda.function_arn,
            properties={
                "Timestamp": str(int(time.time()))  # Force update on every deploy
            }
        )
        
        logger.debug("Bootstrap trigger created successfully") 