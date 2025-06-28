from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_elasticloadbalancingv2 as elbv2,
    aws_logs as logs,
    aws_iam as iam,
    aws_ssm as ssm,
    Duration,
    CfnOutput,
    RemovalPolicy,
    Fn
)
from constructs import Construct
import aws_cdk as cdk
import platform
from . import setup_logger
import logging
import boto3

logger = logging.getLogger(__name__)

class FrontendStack(Stack):
    """
    Simplified frontend stack that:
    - Uses private subnets only (no public subnets)
    - Creates ECS Fargate service for Streamlit application in private egress subnets
    - Creates Internal Application Load Balancer in private egress subnets (HTTP only)
    - Removes AWS Cognito authentication (simplified access via EC2 bastion)
    - Access controlled through EC2 bastion host with SSH tunneling
    """

    def __init__(self, scope: Construct, construct_id: str,
                 backend_stack,
                 project_name: str,
                 vpc_id: str = None,
                 vpc_cidr_block: str = None,
                 private_egress_subnet_1: str = None,
                 private_egress_subnet_2: str = None,
                 private_isolated_subnet_1: str = None,
                 private_isolated_subnet_2: str = None,
                 security_group: str = None,
                 backend_vpc=None,  # VPC reference from backend stack
                 # API Database configuration (external database for data analysis)
                 api_db_host: str = "",
                 api_db_port: int = 5432,
                 api_db_name: str = "",
                 api_db_user: str = "",
                 api_db_password: str = "",
                 api_db_type: str = "",
                 metadata_s3_bucket: str = None,
                 metadata_is_meta: bool = True,
                 metadata_table_meta: str = None,
                 metadata_column_meta: str = None,
                 metadata_metric_meta: str = None,
                 metadata_table_access: str = None,
                 sql_model_id: str = None,
                 chat_model_id: str = None,
                 embedding_model_id: str = None,
                 approach: str = "few_shot",
                 domain_name: str = None,
                 hosted_zone_id: str = None,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.template_options.description = f"{project_name} (uksb-vhbajid3y7) (tag: Frontend)"
        self.project_name = project_name
        self.backend_stack = backend_stack
        
        # Store subnet configuration
        self.private_egress_subnet_1 = private_egress_subnet_1
        self.private_egress_subnet_2 = private_egress_subnet_2
        self.private_isolated_subnet_1 = private_isolated_subnet_1
        self.private_isolated_subnet_2 = private_isolated_subnet_2
        
        # Store API database configuration (external database for data analysis)
        self.api_db_host = api_db_host
        self.api_db_port = api_db_port
        self.api_db_name = api_db_name
        self.api_db_user = api_db_user
        self.api_db_password = api_db_password
        self.api_db_type = api_db_type
        
        # Store metadata configuration
        self.metadata_s3_bucket = metadata_s3_bucket
        self.metadata_is_meta = metadata_is_meta
        self.metadata_table_meta = metadata_table_meta
        self.metadata_column_meta = metadata_column_meta
        self.metadata_metric_meta = metadata_metric_meta
        self.metadata_table_access = metadata_table_access
        
        # Store model configuration
        self.sql_model_id = sql_model_id
        self.chat_model_id = chat_model_id
        self.embedding_model_id = embedding_model_id
        self.approach = approach
        
        # Store domain and certificate configuration
        self.domain_name = domain_name
        self.hosted_zone_id = hosted_zone_id

        logger.debug(f"Initializing FrontendStack for project: {project_name}")

        # Setup VPC infrastructure based on provided parameters
        self._setup_vpc_infrastructure(
            vpc_id, vpc_cidr_block,
            private_egress_subnet_1, private_egress_subnet_2,
            private_isolated_subnet_1, private_isolated_subnet_2,
            security_group, backend_vpc
        )

        # Create CloudWatch Log Group
        logger.debug("Creating CloudWatch Log Group...")
        self.log_group = logs.LogGroup(
            self, "StreamlitLogGroup",
            log_group_name=f"/{self.project_name}-streamlit-ui",
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_WEEK
        )

        # Create ECS Cluster
        logger.debug("Creating ECS Cluster...")
        self.cluster = ecs.Cluster(
            self, "StreamlitCluster",
            cluster_name=f"{project_name}-streamlit-cluster",
            vpc=self.vpc,
            container_insights=True
        )

        # Create task execution role
        self.task_execution_role = iam.Role(
            self, "TaskExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonECSTaskExecutionRolePolicy")
            ]
        )

        # Add CloudWatch logs permissions to task execution role
        self.task_execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                resources=[self.log_group.log_group_arn]
            )
        )

        # Create task role for application permissions
        self.task_role = iam.Role(
            self, "TaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonBedrockFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3FullAccess")
            ]
        )

        # Add Parameter Store permissions to task role
        self.task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ssm:GetParameter",
                    "ssm:GetParameters"
                ],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/{self.project_name}/api/key",
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/{self.project_name}/api-key-id",
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/{self.project_name}/api/endpoint"
                ]
            )
        )
        
        # Add API Gateway permissions to task role for fetching API key values
        self.task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "apigateway:GET"
                ],
                resources=[
                    f"arn:aws:apigateway:{self.region}::/apikeys",
                    f"arn:aws:apigateway:{self.region}::/apikeys/*"
                ]
            )
        )

        # Add Athena and Glue permissions to task role for S3-Athena support
        self.task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "athena:*",
                    "glue:GetDatabase",
                    "glue:GetDatabases",
                    "glue:GetTable",
                    "glue:GetTables",
                    "glue:GetPartition",
                    "glue:GetPartitions"
                ],
                resources=["*"]
            )
        )

        # Create EC2 bastion host for access (move this before Fargate service)
        self._create_bastion_host()

        # Create Internal Fargate service (no public access, HTTP only)
        self._create_internal_fargate_service()

        # Auto-scaling configuration for the Fargate service
        logger.debug("Configuring auto-scaling for Fargate service...")
        scalable_target = self.fargate_service.auto_scale_task_count(
            min_capacity=1,
            max_capacity=5
        )

        # CPU-based scaling
        scalable_target.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=80,
            scale_in_cooldown=Duration.minutes(5),
            scale_out_cooldown=Duration.minutes(2)
        )

        # Memory-based scaling
        scalable_target.scale_on_memory_utilization(
            "MemoryScaling",
            target_utilization_percent=80,
            scale_in_cooldown=Duration.minutes(5),
            scale_out_cooldown=Duration.minutes(2)
        )

        logger.debug("Auto-scaling configuration applied to Fargate service")

        # Consolidated outputs section
        CfnOutput(
            self, "StreamlitAppInternalURL",
            value=f"http://{self.alb.load_balancer_dns_name}",
            description="Internal Streamlit Application URL - Access via EC2 bastion host",
            export_name=f"{self.project_name}-internal-app-url"
        )
        
        CfnOutput(
            self, "BastionHostInstanceId",
            value=self.bastion_instance.instance_id,
            description="EC2 Bastion Host Instance ID for Session Manager access",
            export_name=f"{self.project_name}-bastion-instance-id"
        )

        logger.debug(f"Frontend stack created successfully for project: {self.project_name}")

    def _setup_vpc_infrastructure(self, vpc_id, vpc_cidr_block,
                                    private_egress_subnet_1, private_egress_subnet_2,
                                    private_isolated_subnet_1, private_isolated_subnet_2,
                                    security_group, backend_vpc):
        """Setup VPC infrastructure based on provided parameters."""
        if vpc_id:
            logger.debug(f"Using existing VPC: {vpc_id}")
            
            # Check if all subnets are provided
            all_subnets_provided = all([
                private_egress_subnet_1, private_egress_subnet_2,
                private_isolated_subnet_1, private_isolated_subnet_2
            ])
            
            if not all_subnets_provided:
                missing_configs = []
                if not vpc_id:
                    missing_configs.append("vpc_id")
                if not vpc_cidr_block:
                    missing_configs.append("vpc_cidr_block (dynamically fetched but missing)")
                if not private_egress_subnet_1:
                    missing_configs.append("private_egress_subnet_1")
                if not private_egress_subnet_2:
                    missing_configs.append("private_egress_subnet_2")
                if not private_isolated_subnet_1:
                    missing_configs.append("private_isolated_subnet_1")
                if not private_isolated_subnet_2:
                    missing_configs.append("private_isolated_subnet_2")
                
                logger.warning(f"Some VPC configurations missing: {', '.join(missing_configs)}")
                logger.debug("Will use existing VPC and available subnets")
            
            if all_subnets_provided:
                logger.debug("All subnets provided - importing existing infrastructure")
                logger.debug(f"  VPC ID: {vpc_id}")
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
            else:
                # Import existing VPC with minimal attributes
                self.vpc = ec2.Vpc.from_lookup(
                    self, "ExistingVPC",
                    vpc_id=vpc_id
                )
            
            # Import or create security group
            if security_group:
                self.security_group = ec2.SecurityGroup.from_security_group_id(
                    self, "ExistingSecurityGroup", security_group
                )
                logger.debug(f"Using existing security group: {security_group}")
                
                # Still need to create ALB security group even when using existing security group
                self.alb_security_group = ec2.SecurityGroup(
                    self, "StreamlitALBSecurityGroup",
                    vpc=self.vpc,
                    description=f"Security group for {self.project_name} ALB",
                    allow_all_outbound=False
                )
                
                # Add HTTP ingress for ALB from VPC
                self.alb_security_group.add_ingress_rule(
                    peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
                    connection=ec2.Port.tcp(80),
                    description="HTTP access from VPC"
                )
                
                # Add HTTPS ingress for ALB from VPC
                self.alb_security_group.add_ingress_rule(
                    peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
                    connection=ec2.Port.tcp(443),
                    description="HTTPS access from VPC"
                )
                
                # Note: Cannot add rules to imported security group
                # The existing security group should already have the necessary rules
                logger.debug(f"Created new ALB security group: {self.alb_security_group.security_group_id}")
            else:
                # Create new security group in existing VPC
                self.security_group = ec2.SecurityGroup(
                    self, "FrontendSecurityGroup",
                    vpc=self.vpc,
                    description=f"Security group for {self.project_name} frontend resources",
                    allow_all_outbound=True
                )
                
                # Create separate security group for ALB
                self.alb_security_group = ec2.SecurityGroup(
                    self, "StreamlitALBSecurityGroup",
                    vpc=self.vpc,
                    description=f"Security group for {self.project_name} ALB",
                    allow_all_outbound=False
                )
                
                # Add HTTP ingress for ALB from VPC
                self.alb_security_group.add_ingress_rule(
                    peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
                    connection=ec2.Port.tcp(80),
                    description="HTTP access from VPC"
                )
                
                # Add HTTPS ingress for ALB from VPC
                self.alb_security_group.add_ingress_rule(
                    peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
                    connection=ec2.Port.tcp(443),
                    description="HTTPS access from VPC"
                )
                
                # Add Streamlit port ingress for Fargate service from ALB
                self.security_group.add_ingress_rule(
                    peer=ec2.Peer.security_group_id(self.alb_security_group.security_group_id),
                    connection=ec2.Port.tcp(8501),
                    description="Streamlit port for ALB health checks and communication"
                )
                
                logger.debug(f"Created new frontend security group: {self.security_group.security_group_id}")
                logger.debug(f"Created new ALB security group: {self.alb_security_group.security_group_id}")
                
        elif backend_vpc:
            logger.debug("Using VPC from backend stack")
            self.vpc = backend_vpc
            
            # Create new security group in backend VPC
            self.security_group = ec2.SecurityGroup(
                self, "FrontendSecurityGroup",
                vpc=self.vpc,
                description=f"Security group for {self.project_name} frontend resources",
                allow_all_outbound=True
            )
            
            # Create separate security group for ALB
            self.alb_security_group = ec2.SecurityGroup(
                self, "StreamlitALBSecurityGroup",
                vpc=self.vpc,
                description=f"Security group for {self.project_name} ALB",
                allow_all_outbound=False
            )
            
            # Add HTTP ingress for ALB from VPC
            self.alb_security_group.add_ingress_rule(
                peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
                connection=ec2.Port.tcp(80),
                description="HTTP access from VPC"
            )
            
            # Add HTTPS ingress for ALB from VPC
            self.alb_security_group.add_ingress_rule(
                peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
                connection=ec2.Port.tcp(443),
                description="HTTPS access from VPC"
            )
            
            # Add Streamlit port ingress for Fargate service from ALB
            self.security_group.add_ingress_rule(
                peer=ec2.Peer.security_group_id(self.alb_security_group.security_group_id),
                connection=ec2.Port.tcp(8501),
                description="Streamlit port for ALB health checks and communication"
            )
            
            logger.debug(f"Using backend VPC: {self.vpc.vpc_id}")
            logger.debug(f"Created new frontend security group: {self.security_group.security_group_id}")
            logger.debug(f"Created new ALB security group: {self.alb_security_group.security_group_id}")
            
        else:
            logger.error("No VPC provided - either vpc_id or backend_vpc must be specified")
            raise ValueError("Frontend stack requires either a VPC ID or a VPC reference from the backend stack")

    def _create_internal_fargate_service(self):
        """Create the internal Fargate service for Streamlit application."""
        logger.debug("Creating Internal Fargate service...")

        # Get platform architecture mapping
        platform_mapping = {
            "x86_64": ecs.CpuArchitecture.X86_64,
            "arm64": ecs.CpuArchitecture.ARM64
        }
        architecture = platform_mapping.get(platform.machine(), ecs.CpuArchitecture.X86_64)

        # Environment variables for the container
        environment_vars = {
            "API_ENDPOINT": self.backend_stack.api_gateway_url,
            "API_KEY_PARAMETER_NAME": f"/{self.project_name}/api/key",
            "API_KEY_ID_PARAMETER_NAME": f"/{self.project_name}/api-key-id",
            "PROJECT_NAME": self.project_name,
            # API Database configuration (external database for data analysis)
            "API_DB_HOST": self.api_db_host,
            "API_DB_PORT": str(self.api_db_port) if self.api_db_port else "",
            "API_DB_NAME": self.api_db_name,
            "API_DB_USER": self.api_db_user,
            "API_DB_PASSWORD": self.api_db_password,
            "API_DB_TYPE": self.api_db_type,
            "S3_BUCKET_NAME": self.backend_stack.application_bucket.bucket_name,
            "AWS_DEFAULT_REGION": self.region,
            # Metadata configuration
            "METADATA_S3_BUCKET": self.metadata_s3_bucket or "",
            "METADATA_IS_META": str(self.metadata_is_meta).lower() if self.metadata_is_meta is not None else "true",
            "METADATA_TABLE_META": self.metadata_table_meta or "",
            "METADATA_COLUMN_META": self.metadata_column_meta or "",
            "METADATA_METRIC_META": self.metadata_metric_meta or "",
            "METADATA_TABLE_ACCESS": self.metadata_table_access or "",
            # Model configuration
            "SQL_MODEL_ID": self.sql_model_id or "",
            "CHAT_MODEL_ID": self.chat_model_id or "",
            "EMBEDDING_MODEL_ID": self.embedding_model_id or "",
            "APPROACH": self.approach or "few_shot",
            # S3-Athena specific environment variables
            "ATHENA_WORKGROUP": self.backend_stack.athena_workgroup.name
        }

        logger.debug(f"Container environment variables: {list(environment_vars.keys())}")

        # Log VPC and subnet information for debugging
        logger.debug(f"Using VPC: {self.vpc.vpc_id}")
        logger.debug(f"Using cluster: {self.cluster.cluster_name}")
        logger.debug(f"Platform architecture: {architecture}")

        # Create the Application Load Balancer explicitly in private isolated subnets
        # Use first 2 isolated subnets (different AZs) for internal ALB
        if hasattr(self, 'private_isolated_subnet_1') and hasattr(self, 'private_isolated_subnet_2') and \
           self.private_isolated_subnet_1 and self.private_isolated_subnet_2:
            # Case 1: Using existing VPC with provided isolated subnets
            alb_subnet_1 = ec2.Subnet.from_subnet_id(
                self, "ALBSubnet1", self.private_isolated_subnet_1
            )
            alb_subnet_2 = ec2.Subnet.from_subnet_id(
                self, "ALBSubnet2", self.private_isolated_subnet_2
            )
            alb_subnet_selection = ec2.SubnetSelection(subnets=[alb_subnet_1, alb_subnet_2])
        else:
            # Case 2: Using backend VPC or existing VPC without specific isolated subnets
            # Use first 2 isolated subnets (different AZs) for internal ALB
            alb_subnet_selection = ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            )
        
        self.alb = elbv2.ApplicationLoadBalancer(
            self, "StreamlitALB",
            vpc=self.vpc,
            internet_facing=False,  # Internal ALB
            vpc_subnets=alb_subnet_selection
        )
        
        # Add security group to ALB
        self.alb.add_security_group(self.alb_security_group)
        
        # Create Fargate Task Definition
        self.task_definition = ecs.FargateTaskDefinition(
            self, "StreamlitTaskDef",
            memory_limit_mib=2048,
            cpu=1024,
            task_role=self.task_role,
            execution_role=self.task_execution_role,
            runtime_platform=ecs.RuntimePlatform(
                operating_system_family=ecs.OperatingSystemFamily.LINUX,
                cpu_architecture=architecture
            )
        )
        
        # Add container to task definition
        self.container = self.task_definition.add_container(
            "streamlit-container",
            image=ecs.ContainerImage.from_asset(
                directory="../streamlit",
                file="Dockerfile"
            ),
            environment=environment_vars,
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="streamlit",
                log_group=self.log_group
            ),
            port_mappings=[
                ecs.PortMapping(
                    container_port=8501,
                    protocol=ecs.Protocol.TCP
                )
            ]
        )
        
        # Create Fargate Service
        # Use available subnets for ECS tasks
        # Check what subnet types are available in the VPC
        if len(self.vpc.private_subnets) > 0:
            # Use private subnets with egress (NAT gateway access) if available
            # This allows ECS tasks to pull Docker images from ECR
            fargate_subnet_selection = ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            )
            logger.debug("Using private egress subnets for Fargate service")
        elif len(self.vpc.isolated_subnets) > 0:
            # Use isolated subnets if no egress subnets are available
            # Note: This requires VPC endpoints for ECR to pull Docker images
            fargate_subnet_selection = ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            )
            logger.debug("Using isolated subnets for Fargate service")
        else:
            # This should not happen, but fallback to any available subnet
            logger.warning("No private or isolated subnets found, using default subnet selection")
            fargate_subnet_selection = ec2.SubnetSelection()
        
        self.fargate_service = ecs.FargateService(
            self, "StreamlitService",
            cluster=self.cluster,
            task_definition=self.task_definition,
            desired_count=1,
            assign_public_ip=False,
            vpc_subnets=fargate_subnet_selection,  # Use egress subnets for ECR access
            security_groups=[self.security_group]
        )
        
        # Create Target Group
        self.target_group = elbv2.ApplicationTargetGroup(
            self, "StreamlitTargetGroup",
            vpc=self.vpc,
            port=8501,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,
            health_check=elbv2.HealthCheck(
                path="/_stcore/health",
                protocol=elbv2.Protocol.HTTP,
                timeout=Duration.seconds(5),
                interval=Duration.seconds(30),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
                healthy_http_codes="200"
            )
        )
        
        # Configure target group deregistration delay
        self.target_group.set_attribute(
            key="deregistration_delay.timeout_seconds", 
            value="10"
        )
        
        # Add Fargate service to target group
        self.target_group.add_target(self.fargate_service)
        
        # Create ALB Listener
        self.listener = self.alb.add_listener(
            "StreamlitListener",
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_target_groups=[self.target_group]
        )

        logger.debug("ApplicationLoadBalancedFargateService created successfully (Internal, HTTP only)")

    def _create_bastion_host(self):
        """Create an EC2 bastion host for secure access to the internal ALB.
        The bastion will work without a public IP using SSM Session Manager and EC2 Instance Connect.
        No SSH keys are required - uses EC2 Instance Connect for temporary key injection.
        """
        logger.debug("Creating EC2 Bastion Host with SSM Session Manager support...")

        # Create bastion security group - no SSH ingress rules needed
        self.bastion_security_group = ec2.SecurityGroup(
            self, "BastionSecurityGroup",
            vpc=self.vpc,
            description=f"Security group for {self.project_name} bastion host",
            allow_all_outbound=True
        )

        # No ingress rules needed - SSM Session Manager doesn't require them
        # The bastion will connect outbound to AWS services via VPC endpoints
        
        # Allow outbound HTTPS to VPC endpoints for SSM connectivity
        self.bastion_security_group.add_egress_rule(
            peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(443),
            description="HTTPS access to VPC endpoints for SSM"
        )

        # Create the bastion instance in egress subnets to match the working architecture
        # When no VPC is provided, bastion is in egress subnets and can reach VPC endpoints
        # VPC endpoints are now also placed in egress subnets for consistency
        if len(self.vpc.private_subnets) > 0:
            # Use private subnets with egress (NAT gateway access) - matches working architecture
            bastion_subnet_selection = ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            )
            logger.debug("Using private egress subnets for bastion host (matches working architecture)")
        elif len(self.vpc.isolated_subnets) > 0:
            # Use isolated subnets if no egress subnets are available
            # This is a fallback scenario
            bastion_subnet_selection = ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            )
            logger.debug("Using isolated subnets for bastion host (fallback)")
        else:
            # This should not happen, but fallback to any available subnet
            logger.warning("No private or isolated subnets found, using default subnet selection")
            bastion_subnet_selection = ec2.SubnetSelection()
        
        self.bastion_instance = ec2.Instance(
            self, "BastionHost",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3,
                ec2.InstanceSize.MICRO
            ),
            machine_image=ec2.AmazonLinuxImage(
                generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2
            ),
            vpc=self.vpc,
            vpc_subnets=bastion_subnet_selection,
            security_group=self.bastion_security_group,
            user_data=ec2.UserData.for_linux()
        )

        # Add Session Manager permissions to bastion
        self.bastion_instance.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
        )

        # Add EC2 Instance Connect permissions for SSH without permanent keys
        self.bastion_instance.role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ec2-instance-connect:SendSSHPublicKey"
                ],
                resources=[
                    f"arn:aws:ec2:{self.region}:{self.account}:instance/*"
                ],
                conditions={
                    "StringEquals": {
                        "ec2:osuser": "ec2-user"
                    }
                }
            )
        )

        # Add user data to install useful tools and configure EC2 Instance Connect
        self.bastion_instance.user_data.add_commands(
            "yum update -y",
            "yum install -y curl wget git jq lynx",
            "# Install AWS CLI v2",
            "curl 'https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip' -o 'awscliv2.zip'",
            "unzip awscliv2.zip",
            "sudo ./aws/install",
            "# Install EC2 Instance Connect",
            "yum install -y ec2-instance-connect",
            "# Install Session Manager Agent (should already be installed on Amazon Linux 2)",
            "yum install -y amazon-ssm-agent",
            "systemctl enable amazon-ssm-agent",
            "systemctl start amazon-ssm-agent",
            "# Wait for network and VPC endpoints to be ready, then restart SSM agent",
            "sleep 30",
            "systemctl restart amazon-ssm-agent",
            "# Verify SSM agent is running",
            "systemctl status amazon-ssm-agent",
            "# Configure DNS for VPC endpoints (ensure resolution works properly)",
            "echo 'options timeout:2 attempts:5' >> /etc/resolv.conf",
            "# Add message of the day",
            "echo '====================================' > /etc/motd",
            "echo 'Data Analyst Bastion Host (No Public IP)' >> /etc/motd",
            "echo 'Access via AWS Session Manager ONLY:' >> /etc/motd",
            "echo 'Session Manager: aws ssm start-session --target <INSTANCE_ID>' >> /etc/motd",
            "echo 'No SSH keys required - uses EC2 Instance Connect' >> /etc/motd",
            "echo 'Get the instance ID from deployment outputs.' >> /etc/motd",
            "echo 'After deployment, use ./access.sh to get connection details.' >> /etc/motd",
            "echo 'Example: curl http://<ALB_DNS_NAME>' >> /etc/motd",
            "echo '====================================' >> /etc/motd"
        )

        logger.debug(f"Bastion host created successfully in private egress subnet (no public IP): {self.bastion_instance.instance_id}") 