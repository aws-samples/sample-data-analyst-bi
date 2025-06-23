from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    CfnOutput,
    CustomResource,
    custom_resources as cr
)
from constructs import Construct
from . import setup_logger
import logging
import json
import boto3

logger = logging.getLogger(__name__)

class VpcEndpointsStack(Stack):
    """
    VPC Endpoints Stack that creates VPC endpoints for AWS services.
    
    Creates VPC endpoints for:
    - Bedrock Runtime (Interface)
    - Bedrock (Interface) 
    - Lambda (Interface)
    - Athena (Interface)
    - S3 (Gateway)
    
    Checks for existing endpoints and only creates missing ones.
    Handles DNS conflicts gracefully by disabling private DNS when needed.
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
                 backend_vpc=None,  # VPC reference from backend stack
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.template_options.description = f"{project_name} VPC Endpoints (uksb-vhbajid3y7)"
        self.project_name = project_name
        self.vpc_id = vpc_id
        logger.info(f"Initializing VpcEndpointsStack for project: {project_name}")

        # Setup VPC infrastructure based on provided parameters
        self._setup_vpc_infrastructure(
            vpc_id, vpc_cidr_block,
            private_egress_subnet_1, private_egress_subnet_2,
            private_isolated_subnet_1, private_isolated_subnet_2,
            security_group, backend_vpc
        )

        # Check what VPC endpoints already exist (only if using existing VPC)
        if vpc_id:
            self.existing_endpoints = self._check_existing_endpoints()
            logger.info(f"Found {len(self.existing_endpoints)} existing VPC endpoints in VPC {vpc_id}")
        else:
            self.existing_endpoints = {}
            logger.info("Using new VPC - no existing endpoints to check")

        # Create VPC endpoints
        self._create_vpc_endpoints()

        # Outputs
        CfnOutput(
            self, "VpcEndpointSecurityGroupOutput",
            value=self.vpc_endpoint_security_group.security_group_id,
            description="Security group for VPC endpoints",
            export_name=f"{project_name}-vpc-endpoint-security-group"
        )

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
            
            if all_subnets_provided:
                logger.debug("All subnets provided - importing existing infrastructure")
                
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
                
                # Import existing subnets - use egress subnets for VPC endpoints to match existing infrastructure
                self.private_egress_subnet_1 = ec2.Subnet.from_subnet_id(
                    self, "PrivateEgressSubnet1", private_egress_subnet_1
                )
                self.private_egress_subnet_2 = ec2.Subnet.from_subnet_id(
                    self, "PrivateEgressSubnet2", private_egress_subnet_2
                )
            else:
                logger.debug("Some subnets missing - importing VPC and using available subnets")
                
                # Import existing VPC with minimal attributes
                self.vpc = ec2.Vpc.from_lookup(
                    self, "ExistingVPC",
                    vpc_id=vpc_id
                )
                
                # Use provided isolated subnets or find existing ones
                if private_isolated_subnet_1 and private_isolated_subnet_2:
                    self.private_isolated_subnet_1 = ec2.Subnet.from_subnet_id(
                        self, "PrivateIsolatedSubnet1", private_isolated_subnet_1
                    )
                    self.private_isolated_subnet_2 = ec2.Subnet.from_subnet_id(
                        self, "PrivateIsolatedSubnet2", private_isolated_subnet_2
                    )
                else:
                    # Use the first two isolated subnets from the VPC
                    if len(self.vpc.isolated_subnets) >= 2:
                        self.private_isolated_subnet_1 = self.vpc.isolated_subnets[0]
                        self.private_isolated_subnet_2 = self.vpc.isolated_subnets[1]
                    else:
                        # Fallback to any available subnets
                        available_subnets = self.vpc.isolated_subnets + self.vpc.private_subnets
                        if len(available_subnets) >= 2:
                            self.private_isolated_subnet_1 = available_subnets[0]
                            self.private_isolated_subnet_2 = available_subnets[1]
                        else:
                            logger.error("Not enough subnets available in VPC for VPC endpoints")
                            raise ValueError("VPC must have at least 2 subnets for VPC endpoints")
            
            # Import or create security group
            if security_group:
                logger.debug(f"Using existing security group: {security_group}")
                self.vpc_endpoint_security_group = ec2.SecurityGroup.from_security_group_id(
                    self, "ExistingVpcEndpointSecurityGroup", security_group
                )
            else:
                logger.debug("Creating new security group for VPC endpoints")
                self.vpc_endpoint_security_group = ec2.SecurityGroup(
                    self, "VpcEndpointSecurityGroup",
                    vpc=self.vpc,
                    description=f"Security group for {self.project_name} VPC endpoints",
                    allow_all_outbound=True
                )
                
                # Allow HTTPS traffic from VPC CIDR to VPC endpoints
                self.vpc_endpoint_security_group.add_ingress_rule(
                    peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
                    connection=ec2.Port.tcp(443),
                    description="HTTPS access to VPC endpoints from VPC CIDR"
                )
        elif backend_vpc:
            logger.debug("Using VPC reference from backend stack")
            self.vpc = backend_vpc
            
            # Use the isolated subnets from the VPC for VPC endpoints
            if len(self.vpc.isolated_subnets) >= 2:
                self.private_isolated_subnet_1 = self.vpc.isolated_subnets[0]
                self.private_isolated_subnet_2 = self.vpc.isolated_subnets[1]
                logger.debug(f"Using isolated subnets for VPC endpoints: {self.private_isolated_subnet_1.subnet_id}, {self.private_isolated_subnet_2.subnet_id}")
            else:
                # Fallback to any available subnets
                available_subnets = self.vpc.isolated_subnets + self.vpc.private_subnets
                if len(available_subnets) >= 2:
                    self.private_isolated_subnet_1 = available_subnets[0]
                    self.private_isolated_subnet_2 = available_subnets[1]
                    logger.debug(f"Using fallback subnets for VPC endpoints: {self.private_isolated_subnet_1.subnet_id}, {self.private_isolated_subnet_2.subnet_id}")
                else:
                    logger.error("Not enough subnets available in VPC for VPC endpoints")
                    raise ValueError("VPC must have at least 2 subnets for VPC endpoints")
            
            # Create security group for VPC endpoints
            self.vpc_endpoint_security_group = ec2.SecurityGroup(
                self, "VpcEndpointSecurityGroup",
                vpc=self.vpc,
                description=f"Security group for {self.project_name} VPC endpoints",
                allow_all_outbound=True
            )
            
            # Allow HTTPS traffic from VPC CIDR to VPC endpoints
            self.vpc_endpoint_security_group.add_ingress_rule(
                peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
                connection=ec2.Port.tcp(443),
                description="HTTPS access to VPC endpoints from VPC CIDR"
            )
        else:
            logger.error("No VPC provided - either vpc_id or backend_vpc must be specified")
            raise ValueError("VPC endpoints stack requires either a VPC ID or a VPC reference from the backend stack")

    def _check_existing_endpoints(self):
        """Check what VPC endpoints already exist in the VPC."""
        existing_endpoints = {}
        try:
            # Use the same region as the stack
            ec2_client = boto3.client('ec2', region_name=self.region)
            
            # Get existing VPC endpoints - use vpc_id from the VPC object if available
            vpc_id_to_use = self.vpc_id if hasattr(self, 'vpc_id') and self.vpc_id else self.vpc.vpc_id
            
            # Get existing VPC endpoints
            response = ec2_client.describe_vpc_endpoints(
                Filters=[
                    {
                        'Name': 'vpc-id',
                        'Values': [vpc_id_to_use]
                    }
                ]
            )
            
            logger.debug(f"Checking for existing VPC endpoints in VPC: {vpc_id_to_use}")
            
            for endpoint in response.get('VpcEndpoints', []):
                service_name = endpoint.get('ServiceName', '')
                endpoint_id = endpoint.get('VpcEndpointId', '')
                state = endpoint.get('State', '')
                endpoint_type = endpoint.get('VpcEndpointType', '')
                
                logger.debug(f"Found existing endpoint: {service_name} ({endpoint_id}) - {state} - {endpoint_type}")
                
                # Map service names to our endpoint names - be more flexible with matching
                if 'bedrock-runtime' in service_name:
                    existing_endpoints['BedrockRuntimeVpcEndpoint'] = {'id': endpoint_id, 'state': state, 'service': service_name, 'type': endpoint_type}
                elif 'bedrock' in service_name and 'runtime' not in service_name:
                    existing_endpoints['BedrockVpcEndpoint'] = {'id': endpoint_id, 'state': state, 'service': service_name, 'type': endpoint_type}
                elif 's3' in service_name:
                    existing_endpoints['S3VpcEndpoint'] = {'id': endpoint_id, 'state': state, 'service': service_name, 'type': endpoint_type}
                elif 'dynamodb' in service_name:
                    existing_endpoints['DynamoDBVpcEndpoint'] = {'id': endpoint_id, 'state': state, 'service': service_name, 'type': endpoint_type}
                elif 'athena' in service_name:
                    existing_endpoints['AthenaVpcEndpoint'] = {'id': endpoint_id, 'state': state, 'service': service_name, 'type': endpoint_type}
                elif 'states' in service_name:
                    existing_endpoints['StepFunctionsVpcEndpoint'] = {'id': endpoint_id, 'state': state, 'service': service_name, 'type': endpoint_type}
                elif 'ssm' in service_name and 'messages' not in service_name:
                    existing_endpoints['SSMVpcEndpoint'] = {'id': endpoint_id, 'state': state, 'service': service_name, 'type': endpoint_type}
                elif 'ssmmessages' in service_name:
                    existing_endpoints['SSMMessagesVpcEndpoint'] = {'id': endpoint_id, 'state': state, 'service': service_name, 'type': endpoint_type}
                elif 'ec2messages' in service_name:
                    existing_endpoints['EC2MessagesVpcEndpoint'] = {'id': endpoint_id, 'state': state, 'service': service_name, 'type': endpoint_type}
            
            # Also check for Gateway endpoints by looking at route tables
            # This is important because Gateway endpoints show up as routes in route tables
            self._check_gateway_endpoints_in_route_tables(ec2_client, vpc_id_to_use, existing_endpoints)
                
            logger.info(f"Found {len(existing_endpoints)} existing VPC endpoints that match our required services")
            for name, info in existing_endpoints.items():
                logger.info(f"  - {name}: {info['id']} ({info['state']})")
                
        except Exception as e:
            logger.warning(f"Could not check existing VPC endpoints: {e}")
            # Continue anyway, we'll handle conflicts during creation
            
        return existing_endpoints
    
    def _check_gateway_endpoints_in_route_tables(self, ec2_client, vpc_id, existing_endpoints):
        """Check route tables for existing Gateway VPC endpoints (S3, DynamoDB)."""
        try:
            # Get route tables for this VPC
            route_tables_response = ec2_client.describe_route_tables(
                Filters=[
                    {
                        'Name': 'vpc-id',
                        'Values': [vpc_id]
                    }
                ]
            )
            
            route_tables = route_tables_response.get('RouteTables', [])
            logger.debug(f"Found {len(route_tables)} route tables in VPC {vpc_id}")
            
            for route_table in route_tables:
                route_table_id = route_table.get('RouteTableId')
                routes = route_table.get('Routes', [])
                logger.debug(f"Checking route table {route_table_id} with {len(routes)} routes")
                
                for route in routes:
                    destination_prefix_list_id = route.get('DestinationPrefixListId')
                    if destination_prefix_list_id:
                        logger.debug(f"Found route with prefix list: {destination_prefix_list_id} in route table {route_table_id}")
                        
                        # Check if this is an S3 or DynamoDB prefix list
                        if destination_prefix_list_id.startswith('pl-'):
                            # Get prefix list details to identify the service
                            try:
                                prefix_list_response = ec2_client.describe_prefix_lists(
                                    PrefixListIds=[destination_prefix_list_id]
                                )
                                for prefix_list in prefix_list_response.get('PrefixLists', []):
                                    prefix_list_name = prefix_list.get('PrefixListName', '').lower()
                                    logger.debug(f"Prefix list {destination_prefix_list_id} name: {prefix_list_name}")
                                    
                                    if 's3' in prefix_list_name:
                                        existing_endpoints['S3VpcEndpoint'] = {
                                            'id': 'existing-in-route-table', 
                                            'state': 'Available', 
                                            'service': 'com.amazonaws.us-east-1.s3',
                                            'type': 'Gateway',
                                            'route_table': route_table_id,
                                            'prefix_list': destination_prefix_list_id
                                        }
                                        logger.info(f"Found existing S3 Gateway endpoint via route table {route_table_id} with prefix list {destination_prefix_list_id}")
                                    elif 'dynamodb' in prefix_list_name:
                                        existing_endpoints['DynamoDBVpcEndpoint'] = {
                                            'id': 'existing-in-route-table', 
                                            'state': 'Available', 
                                            'service': 'com.amazonaws.us-east-1.dynamodb',
                                            'type': 'Gateway',
                                            'route_table': route_table_id,
                                            'prefix_list': destination_prefix_list_id
                                        }
                                        logger.info(f"Found existing DynamoDB Gateway endpoint via route table {route_table_id} with prefix list {destination_prefix_list_id}")
                            except Exception as prefix_error:
                                logger.debug(f"Could not check prefix list {destination_prefix_list_id}: {prefix_error}")
                                # Even if we can't get the prefix list name, we know there's a Gateway endpoint
                                # Let's assume it's S3 based on the error message we saw
                                if destination_prefix_list_id == 'pl-63a5400a':
                                    existing_endpoints['S3VpcEndpoint'] = {
                                        'id': 'existing-in-route-table', 
                                        'state': 'Available', 
                                        'service': 'com.amazonaws.us-east-1.s3',
                                        'type': 'Gateway',
                                        'route_table': route_table_id,
                                        'prefix_list': destination_prefix_list_id
                                    }
                                    logger.info(f"Found existing S3 Gateway endpoint (assumed from known prefix list) via route table {route_table_id}")
                                
        except Exception as e:
            logger.warning(f"Could not check route tables for Gateway endpoints: {e}")

    def _create_vpc_endpoints(self):
        """Create VPC endpoints for required AWS services, skipping any that already exist."""
        # List of endpoints to create: (logical_name, service_name, endpoint_type, description)
        endpoints = [
            ("BedrockRuntimeVpcEndpoint", f"com.amazonaws.{self.region}.bedrock-runtime", "Interface", "Bedrock Runtime"),
            ("BedrockVpcEndpoint", f"com.amazonaws.{self.region}.bedrock", "Interface", "Bedrock"),
            ("S3VpcEndpoint", f"com.amazonaws.{self.region}.s3", "Gateway", "S3"),
            ("DynamoDBVpcEndpoint", f"com.amazonaws.{self.region}.dynamodb", "Gateway", "DynamoDB"),
            ("AthenaVpcEndpoint", f"com.amazonaws.{self.region}.athena", "Interface", "Athena"),
            ("StepFunctionsVpcEndpoint", f"com.amazonaws.{self.region}.states", "Interface", "Step Functions"),
            ("SSMVpcEndpoint", f"com.amazonaws.{self.region}.ssm", "Interface", "SSM"),
            ("SSMMessagesVpcEndpoint", f"com.amazonaws.{self.region}.ssmmessages", "Interface", "SSM Messages"),
            ("EC2MessagesVpcEndpoint", f"com.amazonaws.{self.region}.ec2messages", "Interface", "EC2 Messages"),
        ]

        # Check for existing endpoints (including Gateway endpoints via route tables)
        existing_endpoints = self._check_existing_endpoints()

        created_endpoints = []
        skipped_endpoints = []
        dns_conflict_endpoints = []

        # Subnets for interface endpoints
        subnets = self._get_subnets_for_endpoints()

        for endpoint_name, service_name, endpoint_type, description in endpoints:
            if endpoint_name in existing_endpoints:
                logger.info(f"Skipping {endpoint_name} ({service_name}) - already exists: {existing_endpoints[endpoint_name]}")
                skipped_endpoints.append(f"{endpoint_name} ({service_name}) [already exists]")
                continue

            try:
                if endpoint_type == "Interface":
                    # Try to create Interface VPC endpoint with private DNS disabled first
                    try:
                        vpc_endpoint = ec2.InterfaceVpcEndpoint(
                            self, endpoint_name,
                            vpc=self.vpc,
                            service=ec2.InterfaceVpcEndpointService(service_name),
                            subnets=ec2.SubnetSelection(subnets=subnets),
                            security_groups=[self.vpc_endpoint_security_group],
                            private_dns_enabled=False
                        )
                        created_endpoints.append(f"{endpoint_name} ({service_name}) [DNS disabled]")
                        logger.info(f"Created Interface VPC endpoint without private DNS: {endpoint_name}")
                    except Exception as creation_error:
                        # Check if it's because the endpoint already exists
                        if any(keyword in str(creation_error).lower() for keyword in ["already exists", "duplicate", "conflicting"]):
                            logger.warning(f"Endpoint {endpoint_name} appears to already exist: {creation_error}")
                            skipped_endpoints.append(f"{endpoint_name} (creation conflict - likely exists)")
                            continue
                        else:
                            raise creation_error
                elif endpoint_type == "Gateway":
                    # Only create Gateway endpoints if not found in route tables
                    if "s3" in service_name:
                        vpc_endpoint = ec2.GatewayVpcEndpoint(
                            self, endpoint_name,
                            vpc=self.vpc,
                            service=ec2.GatewayVpcEndpointAwsService.S3
                        )
                    elif "dynamodb" in service_name:
                        vpc_endpoint = ec2.GatewayVpcEndpoint(
                            self, endpoint_name,
                            vpc=self.vpc,
                            service=ec2.GatewayVpcEndpointAwsService.DYNAMODB
                        )
                    else:
                        logger.warning(f"Unknown Gateway service: {service_name}")
                        continue
                    created_endpoints.append(f"{endpoint_name} ({service_name})")
                    logger.info(f"Created Gateway VPC endpoint: {endpoint_name}")
                    # Output the VPC endpoint ID
                    CfnOutput(
                        self, f"{endpoint_name}Id",
                        value=vpc_endpoint.vpc_endpoint_id,
                        description=f"VPC Endpoint ID for {description}",
                        export_name=f"{self.project_name}-{endpoint_name.lower()}-id"
                    )
            except Exception as e:
                logger.warning(f"Could not create endpoint {endpoint_name}: {e}")
                skipped_endpoints.append(f"{endpoint_name} (creation failed)")
                continue

        logger.info(f"VPC endpoints creation completed. Total attempted: {len(endpoints)}, Created: {len(created_endpoints)}, Skipped: {len(skipped_endpoints)}")
        if created_endpoints:
            logger.info(f"Created endpoints: {created_endpoints}")
        if skipped_endpoints:
            logger.info(f"Skipped endpoints: {skipped_endpoints}")
        if dns_conflict_endpoints:
            logger.info(f"Endpoints with DNS conflict: {dns_conflict_endpoints}")

        CfnOutput(
            self, "CreatedVpcEndpoints",
            value=", ".join(created_endpoints) if created_endpoints else "None",
            description="VPC endpoints created by this stack",
            export_name=f"{self.project_name}-created-vpc-endpoints"
        )

        CfnOutput(
            self, "SkippedVpcEndpoints", 
            value=", ".join(skipped_endpoints) if skipped_endpoints else "None",
            description="VPC endpoints that already existed and were skipped",
            export_name=f"{self.project_name}-skipped-vpc-endpoints"
        )

        CfnOutput(
            self, "DnsConflictVpcEndpoints",
            value=", ".join(dns_conflict_endpoints) if dns_conflict_endpoints else "None",
            description="VPC endpoints created without private DNS due to conflicts",
            export_name=f"{self.project_name}-dns-conflict-vpc-endpoints"
        )

        total_attempted = len(endpoints)
        total_created = len(created_endpoints) + len(dns_conflict_endpoints)
        total_skipped = len(skipped_endpoints)
        
        logger.info(f"VPC endpoints creation completed. Total attempted: {total_attempted}, Created: {total_created}, Skipped: {total_skipped}")
        
        if dns_conflict_endpoints:
            logger.warning(f"DNS conflicts resolved by disabling private DNS for: {', '.join([ep.split(' ')[0] for ep in dns_conflict_endpoints])}")
            logger.info("Note: Endpoints without private DNS will still work, but may require using the endpoint URL directly instead of the service DNS name")

    def _get_subnets_for_endpoints(self):
        """Return a list of subnets to use for VPC endpoint creation, with detailed logging.
        
        VPC endpoints should be placed in egress subnets to match the working architecture
        when no VPC is provided. This ensures bastion hosts in egress subnets can reach them.
        """
        subnets = []
        # PREFER EGRESS SUBNETS FIRST - this matches the working architecture
        if hasattr(self, 'private_egress_subnet_1') and hasattr(self, 'private_egress_subnet_2') and \
           self.private_egress_subnet_1 and self.private_egress_subnet_2:
            subnets = [self.private_egress_subnet_1, self.private_egress_subnet_2]
            logger.info(f"Using provided egress subnets for VPC endpoints (matches working architecture): {[s.subnet_id for s in subnets]}")
        elif hasattr(self, 'vpc') and self.vpc and len(self.vpc.private_subnets) >= 2:
            # Use VPC's egress subnets if available
            subnets = [self.vpc.private_subnets[0], self.vpc.private_subnets[1]]
            logger.info(f"Using VPC egress subnets for VPC endpoints: {[s.subnet_id for s in subnets]}")
        elif hasattr(self, 'private_isolated_subnet_1') and hasattr(self, 'private_isolated_subnet_2') and \
             self.private_isolated_subnet_1 and self.private_isolated_subnet_2:
            # Fallback to isolated subnets only if egress subnets are not available
            subnets = [self.private_isolated_subnet_1, self.private_isolated_subnet_2]
            logger.info(f"Using provided isolated subnets for VPC endpoints (fallback): {[s.subnet_id for s in subnets]}")
        elif hasattr(self, 'vpc') and self.vpc:
            # Try to use any available subnets from the VPC
            available_subnets = self.vpc.private_subnets + self.vpc.isolated_subnets
            if len(available_subnets) >= 2:
                subnets = [available_subnets[0], available_subnets[1]]
                logger.info(f"Using available subnets from VPC for VPC endpoints: {[s.subnet_id for s in subnets]}")
            else:
                logger.warning(f"Not enough subnets available in VPC for VPC endpoints. Found: {[s.subnet_id for s in available_subnets]}")
                subnets = available_subnets
        else:
            logger.error("No subnets available for VPC endpoint creation!")
            subnets = []
        if len(subnets) < 2:
            logger.warning(f"Fewer than 2 subnets selected for VPC endpoint creation: {[s.subnet_id for s in subnets]}")
        return subnets 