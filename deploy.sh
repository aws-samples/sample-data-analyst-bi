#!/bin/bash

# Comprehensive deployment script for Data Analyst platform
# Handles deployment, destruction, status checking, and validation

set -e  # Exit on any error

export JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=true

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Default values
PROJECT_NAME="data-analyst"
AWS_REGION=""

# Usage information
show_usage() {
    echo "Usage: $0 [OPTIONS] [COMMAND]"
    echo "Deploy and manage the Data Analyst platform."
    echo ""
    echo "Commands:"
    echo "  deploy           Deploy the complete infrastructure"
    echo "  destroy          Destroy all infrastructure"
    echo "  redeploy         Destroy and redeploy all infrastructure"
    echo "  status           Check deployment status"
    echo "  validate         Validate configuration before deployment"
    echo "  bootstrap        Bootstrap CDK (one-time setup)"
    echo "  build-layers     Build custom Lambda layers only"
    echo "  cleanup          Clean up build artifacts and temporary files"
    echo ""
    echo "Options:"
    echo "  -h, --help                Show this help message"
    echo "  -p, --profile PROFILE     AWS profile to use (required)"
    echo "  -r, --region REGION       AWS region to use (default: from AWS profile config)"
    echo "  -n, --project-name NAME   Project name (default: $PROJECT_NAME)"
    echo "  -v, --verbose             Enable verbose output"
    echo ""
    echo "Examples:"
    echo "  $0 validate               # Validate configuration"
    echo "  $0 bootstrap              # One-time CDK bootstrap"
    echo "  $0 build-layers           # Build custom Lambda layers only"
    echo "  $0 deploy                 # Deploy infrastructure"
    echo "  $0 redeploy               # Destroy and redeploy infrastructure"
    echo "  $0 status                 # Check deployment status"
    echo "  $0 destroy                # Clean up all resources"
    echo "  $0 cleanup                # Clean build artifacts"
}

# Parse arguments
COMMAND=""
VERBOSE=false
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_usage
            exit 0
            ;;
        -p|--profile)
            AWS_PROFILE="$2"
            shift 2
            ;;
        -r|--region)
            AWS_REGION="$2"
            shift 2
            ;;
        -n|--project-name)
            PROJECT_NAME="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        deploy|destroy|redeploy|status|validate|bootstrap|build-layers|cleanup)
            COMMAND="$1"
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

if [ -z "$COMMAND" ]; then
    print_error "No command specified"
    show_usage
    exit 1
fi

# Validate AWS_PROFILE is set
if [ -z "$AWS_PROFILE" ]; then
    print_error "AWS_PROFILE is not set!"
    print_error ""
    print_error "Please set the AWS profile using one of these methods:"
    print_error "  1. Set environment variable: export AWS_PROFILE=your-profile-name"
    print_error "  2. Use the -p option: $0 -p your-profile-name [command]"
    print_error ""
    print_error "Examples:"
    print_error "  export AWS_PROFILE=default && $0 deploy"
    print_error "  $0 -p default deploy"
    print_error ""
    print_error "To list available AWS profiles, run: aws configure list-profiles"
    exit 1
fi

# Set region - use provided region or get from AWS profile config
if [ -z "$AWS_REGION" ]; then
    AWS_REGION=$(aws configure get region --profile $AWS_PROFILE 2>/dev/null || echo "us-east-1")
    print_status "Using region from AWS profile config: $AWS_REGION"
else
    print_status "Using specified region: $AWS_REGION"
fi

# Export AWS profile and region
export AWS_PROFILE=$AWS_PROFILE
export AWS_DEFAULT_REGION=$AWS_REGION

print_status "Using AWS profile: $AWS_PROFILE"
print_status "Using AWS region: $AWS_REGION"
print_status "Project name: $PROJECT_NAME"

# Function to check if CDK is installed
check_cdk_installed() {
    if ! command -v cdk &> /dev/null; then
        print_error "AWS CDK is not installed. Please install it first:"
        print_error "npm install -g aws-cdk"
        exit 1
    fi
    
    if $VERBOSE; then
        CDK_VERSION=$(cdk --version)
        print_status "CDK version: $CDK_VERSION"
    fi
}

# Function to check if AWS CLI is configured
check_aws_configured() {
    if ! aws sts get-caller-identity --profile $AWS_PROFILE --region $AWS_REGION &> /dev/null; then
        print_error "AWS CLI not configured for profile '$AWS_PROFILE' in region '$AWS_REGION'"
        print_error "Run: aws configure --profile $AWS_PROFILE"
        exit 1
    fi
    
    if $VERBOSE; then
        ACCOUNT=$(aws sts get-caller-identity --profile $AWS_PROFILE --region $AWS_REGION --query Account --output text)
        print_status "AWS Account: $ACCOUNT"
        print_status "AWS Region: $AWS_REGION"
    fi
}

# Function to verify configuration
validate_configuration() {
    print_status "Validating configuration..."
    
    if [ ! -f "cdk/cdk.json" ]; then
        print_error "cdk.json not found. Please ensure you're in the project root directory."
        exit 1
    fi
    
    # Check VPC configuration
    VPC_ID=$(grep -o '"vpc_id": "[^"]*"' cdk/cdk.json | cut -d'"' -f4)
    PRIVATE_EGRESS_SUBNET_1=$(grep -o '"private_egress_subnet_1": "[^"]*"' cdk/cdk.json | cut -d'"' -f4)
    PRIVATE_EGRESS_SUBNET_2=$(grep -o '"private_egress_subnet_2": "[^"]*"' cdk/cdk.json | cut -d'"' -f4)
    PRIVATE_ISOLATED_SUBNET_1=$(grep -o '"private_isolated_subnet_1": "[^"]*"' cdk/cdk.json | cut -d'"' -f4)
    PRIVATE_ISOLATED_SUBNET_2=$(grep -o '"private_isolated_subnet_2": "[^"]*"' cdk/cdk.json | cut -d'"' -f4)
    
    if [ -z "$VPC_ID" ]; then
        print_status "🆕 New VPC Deployment Mode"
        print_status "No VPC ID provided - CDK will create a new VPC with all required infrastructure:"
        print_status "  • New VPC with appropriate CIDR block"
        print_status "  • 4 private isolated subnets (2 for Lambda functions, 2 for databases)"
        print_status "  • Security groups with appropriate rules"
        print_status "  • VPC endpoints for AWS services (S3, DynamoDB, Bedrock, Athena, Step Functions, SSM, STS)"
        print_status "  • No NAT Gateway required - VPC endpoints provide AWS service access"
        print_success "✅ Ready for new VPC deployment"
    else
        # Check if all subnets are provided
        if [ -n "$PRIVATE_EGRESS_SUBNET_1" ] && [ -n "$PRIVATE_EGRESS_SUBNET_2" ] && \
           [ -n "$PRIVATE_ISOLATED_SUBNET_1" ] && [ -n "$PRIVATE_ISOLATED_SUBNET_2" ]; then
            print_status "🔗 Existing Infrastructure Mode"
            print_status "Using existing VPC with all subnets provided:"
            print_status "  • VPC ID: $VPC_ID"
            print_status "  • Private Egress Subnets: $PRIVATE_EGRESS_SUBNET_1, $PRIVATE_EGRESS_SUBNET_2"
            print_status "  • Private Isolated Subnets: $PRIVATE_ISOLATED_SUBNET_1, $PRIVATE_ISOLATED_SUBNET_2"
            
            # Verify AWS resources exist
            print_status "Verifying AWS resources..."
            if ! aws ec2 describe-vpcs --vpc-ids $VPC_ID --profile $AWS_PROFILE --region $AWS_REGION &> /dev/null; then
                print_error "VPC $VPC_ID not found or not accessible in region $AWS_REGION"
                exit 1
            fi
            print_success "✅ All existing infrastructure verified"
        else
            print_status "🔧 Hybrid Mode"
            print_status "Using existing VPC with some missing subnets - CDK will create missing components:"
            print_status "  • VPC ID: $VPC_ID (existing)"
            
            missing_subnets=()
            if [ -z "$PRIVATE_EGRESS_SUBNET_1" ]; then
                missing_subnets+=("private_egress_subnet_1")
            fi
            if [ -z "$PRIVATE_EGRESS_SUBNET_2" ]; then
                missing_subnets+=("private_egress_subnet_2")
            fi
            if [ -z "$PRIVATE_ISOLATED_SUBNET_1" ]; then
                missing_subnets+=("private_isolated_subnet_1")
            fi
            if [ -z "$PRIVATE_ISOLATED_SUBNET_2" ]; then
                missing_subnets+=("private_isolated_subnet_2")
            fi
            
            if [ ${#missing_subnets[@]} -gt 0 ]; then
                print_status "  • Missing subnets (will be created): ${missing_subnets[*]}"
            fi
            
            # Verify VPC exists
            print_status "Verifying VPC exists..."
            if ! aws ec2 describe-vpcs --vpc-ids $VPC_ID --profile $AWS_PROFILE --region $AWS_REGION &> /dev/null; then
                print_error "VPC $VPC_ID not found or not accessible in region $AWS_REGION"
                exit 1
            fi
            print_success "✅ Ready for hybrid deployment"
        fi
    fi
    
    print_success "Configuration validation completed successfully"
    
    if $VERBOSE; then
        echo ""
        echo "===================== DEPLOYMENT MODES ====================="
        echo "1. New VPC Mode: Leave vpc_id empty in cdk.json"
        echo "2. Existing Infrastructure Mode: Provide all VPC and subnet IDs"
        echo "3. Hybrid Mode: Provide vpc_id, CDK creates missing subnets"
        echo "============================================================="
        echo ""
    fi
}

# Function to bootstrap CDK
bootstrap_cdk() {
    print_status "Bootstrapping CDK..."
    
    check_cdk_installed
    check_aws_configured
    
    cd cdk
    
    # Check if CDKToolkit stack already exists
    ACCOUNT=$(aws sts get-caller-identity --profile $AWS_PROFILE --region $AWS_REGION --query Account --output text)
    CDK_TOOLKIT_STACK="CDKToolkit"
    
    if aws cloudformation describe-stacks --stack-name "$CDK_TOOLKIT_STACK" --profile $AWS_PROFILE --region $AWS_REGION &> /dev/null; then
        print_success "✅ Using existing CDKToolkit stack"
        if $VERBOSE; then
            TOOLKIT_STATUS=$(aws cloudformation describe-stacks --stack-name "$CDK_TOOLKIT_STACK" --profile $AWS_PROFILE --region $AWS_REGION --query "Stacks[0].StackStatus" --output text)
            print_status "CDKToolkit status: $TOOLKIT_STATUS"
        fi
    else
        print_warning "CDKToolkit not found. Bootstrapping CDK..."
        print_status "Creating CDKToolkit stack in account $ACCOUNT, region $AWS_REGION"
        cdk bootstrap --profile $AWS_PROFILE
        print_success "CDK bootstrap completed - ready for deployment"
    fi
}

# Function to build custom Lambda layers
build_custom_layers() {
    print_status "Building custom Lambda layers..."
    
    local current_dir=$(pwd)
    cd layers
    
    # Build data-analyst custom layer
    print_status "Building data-analyst custom layer..."
    if [ ! -f "Dockerfile-data-analyst" ]; then
        print_error "Dockerfile-data-analyst not found in layers directory"
        exit 1
    fi
    
    if [ ! -f "data-analyst-requirements.txt" ]; then
        print_error "data-analyst-requirements.txt not found in layers directory"
        exit 1
    fi
    
    print_status "Creating data-analyst layer with Docker..."
    docker buildx build --platform linux/amd64 -t data-analyst-lambda-layer -f Dockerfile-data-analyst . --load
    docker run --platform linux/amd64 --name data-analyst-lambda-layer-container -v "$(pwd):/app" data-analyst-lambda-layer
    docker stop data-analyst-lambda-layer-container
    docker rm data-analyst-lambda-layer-container
    docker rmi --force data-analyst-lambda-layer
    
    if [ ! -f "data-analyst-custom-layer.zip" ]; then
        print_error "Failed to create data-analyst-custom-layer.zip"
        exit 1
    fi
    print_success "✅ Data-analyst custom layer created: data-analyst-custom-layer.zip"
    
    # Build querybot custom layer
    print_status "Building querybot custom layer..."
    if [ ! -f "Dockerfile-querybot" ]; then
        print_error "Dockerfile-querybot not found in layers directory"
        exit 1
    fi
    
    if [ ! -f "querybot-requirements.txt" ]; then
        print_error "querybot-requirements.txt not found in layers directory"
        exit 1
    fi
    
    print_status "Creating querybot layer with Docker..."
    docker buildx build --platform linux/amd64 -t querybot-lambda-layer -f Dockerfile-querybot . --load
    docker run --platform linux/amd64 --name querybot-lambda-layer-container -v "$(pwd):/app" querybot-lambda-layer
    docker stop querybot-lambda-layer-container
    docker rm querybot-lambda-layer-container
    docker rmi --force querybot-lambda-layer
    
    if [ ! -f "querybot-custom-layer.zip" ]; then
        print_error "Failed to create querybot-custom-layer.zip"
        exit 1
    fi
    print_success "✅ Querybot custom layer created: querybot-custom-layer.zip"
    
    cd "$current_dir"
    print_success "Custom Lambda layers built successfully!"
}

# Function to deploy infrastructure
deploy_infrastructure() {
    print_status "Deploying Data Analyst platform..."
    
    check_cdk_installed
    check_aws_configured
    validate_configuration
    
    # Build custom layers before deployment
    build_custom_layers
    
    print_status "Checking if CDK is bootstrapped..."
    cd cdk
    
    # Check if CDKToolkit stack already exists
    ACCOUNT=$(aws sts get-caller-identity --profile $AWS_PROFILE --region $AWS_REGION --query Account --output text)
    CDK_TOOLKIT_STACK="ipd-cet-stack"
    
    if aws cloudformation describe-stacks --stack-name "$CDK_TOOLKIT_STACK" --profile $AWS_PROFILE --region $AWS_REGION &> /dev/null; then
        print_success "✅ Using existing CDKToolkit stack"
        if $VERBOSE; then
            TOOLKIT_STATUS=$(aws cloudformation describe-stacks --stack-name "$CDK_TOOLKIT_STACK" --profile $AWS_PROFILE --region $AWS_REGION --query "Stacks[0].StackStatus" --output text)
            print_status "CDKToolkit status: $TOOLKIT_STATUS"
        fi
    else
        print_warning "CDKToolkit not found. Bootstrapping CDK..."
        print_status "Creating CDKToolkit stack in account $ACCOUNT, region $AWS_REGION"
        cdk bootstrap --profile $AWS_PROFILE
        print_success "CDK bootstrap completed - ready for deployment"
    fi
    
    print_status "Synthesizing CDK app..."
    cdk synth --profile $AWS_PROFILE
    
    print_status "Deploying VPC endpoints stack (required for SSM connectivity)..."
    cdk deploy ${PROJECT_NAME}-vpc-endpoints --require-approval never --profile $AWS_PROFILE
    
    print_status "Deploying backend stack..."
    cdk deploy ${PROJECT_NAME}-backend --require-approval never --profile $AWS_PROFILE
    
    print_status "Deploying frontend stack..."
    cdk deploy ${PROJECT_NAME}-frontend --require-approval never --profile $AWS_PROFILE
    
    print_success "Deployment completed successfully!"
    echo ""
    print_status "🎉 Your Data Analyst platform is now deployed!"
    print_status "VPC endpoints have been created for SSM connectivity"
    print_status "Use './ssh_tunnel.sh' to get access instructions"
}

# Function to redeploy infrastructure (destroy + deploy)
redeploy_infrastructure() {
    print_warning "⚠️  This will DESTROY ALL resources and then REDEPLOY the Data Analyst platform."
    print_warning "This action is irreversible and will delete all existing data!"
    print_warning "The complete infrastructure will be rebuilt from scratch."
    echo ""
    read -p "Are you sure you want to destroy and redeploy? Type 'yes' to confirm: " -r
    echo
    if [[ ! $REPLY = "yes" ]]; then
        print_status "Redeploy cancelled."
        exit 0
    fi
    
    print_status "Starting redeploy process..."
    echo ""
    
    # Step 1: Destroy existing infrastructure
    print_status "🗑️  Phase 1: Destroying existing infrastructure..."
    
    cd cdk
    
    # Destroy frontend first (dependencies)
    print_status "Destroying frontend stack..."
    cdk destroy ${PROJECT_NAME}-frontend --force --profile $AWS_PROFILE || print_warning "Frontend stack may not exist"
    
    print_status "Destroying backend stack..."
    cdk destroy ${PROJECT_NAME}-backend --force --profile $AWS_PROFILE || print_warning "Backend stack may not exist"
    
    print_status "Destroying VPC endpoints stack..."
    cdk destroy ${PROJECT_NAME}-vpc-endpoints --force --profile $AWS_PROFILE || print_warning "VPC endpoints stack may not exist"
    
    print_success "✅ Destruction phase completed!"
    echo ""
    
    # Step 2: Deploy new infrastructure
    print_status "🚀 Phase 2: Deploying fresh infrastructure..."
    
    # Validate configuration before deployment
    cd ..
    validate_configuration
    
    # Build custom layers before deployment
    build_custom_layers
    
    cd cdk
    
    # Check if CDK is bootstrapped
    ACCOUNT=$(aws sts get-caller-identity --profile $AWS_PROFILE --region $AWS_REGION --query Account --output text)
    CDK_TOOLKIT_STACK="CDKToolkit"
    
    if aws cloudformation describe-stacks --stack-name "$CDK_TOOLKIT_STACK" --profile $AWS_PROFILE --region $AWS_REGION &> /dev/null; then
        print_success "✅ Using existing CDKToolkit stack"
    else
        print_warning "CDKToolkit not found. Bootstrapping CDK..."
        cdk bootstrap --profile $AWS_PROFILE
        print_success "CDK bootstrap completed"
    fi
    
    print_status "Synthesizing CDK app..."
    cdk synth --profile $AWS_PROFILE
    
    print_status "Deploying VPC endpoints stack..."
    cdk deploy ${PROJECT_NAME}-vpc-endpoints --require-approval never --profile $AWS_PROFILE
    
    print_status "Deploying backend stack..."
    cdk deploy ${PROJECT_NAME}-backend --require-approval never --profile $AWS_PROFILE
    
    print_status "Deploying frontend stack..."
    cdk deploy ${PROJECT_NAME}-frontend --require-approval never --profile $AWS_PROFILE
    
    print_success "✅ Deployment phase completed!"
    echo ""
    print_success "🎉 Redeploy completed successfully!"
    print_status "Your Data Analyst platform has been completely rebuilt!"
    print_status "Use './ssh_tunnel.sh' to get access instructions"
}

# Function to destroy infrastructure
destroy_infrastructure() {
    print_warning "⚠️  This will destroy ALL resources for the Data Analyst platform:"
    print_warning "   • VPC Endpoints (SSM, S3, Lambda, etc.)"
    print_warning "   • RDS PostgreSQL database and ALL data"
    print_warning "   • Lambda functions and custom layers"
    print_warning "   • API Gateway and API keys"
    print_warning "   • S3 bucket and ALL stored data"
    print_warning "   • DynamoDB table and project data"
    print_warning "   • Athena workgroup and query results"
    print_warning "   • Step Functions workflows"
    print_warning "   • Bedrock guardrails"
    print_warning "   • ECS cluster and Streamlit application"
    print_warning "   • Application Load Balancer"
    print_warning "   • CloudWatch logs and metrics"
    print_warning ""
    print_warning "⚠️  This action is IRREVERSIBLE and will DELETE ALL DATA!"
    print_warning "⚠️  Force deletion is enabled - NO rollback on failures!"
    echo ""
    read -p "Are you sure you want to destroy all infrastructure? Type 'yes' to confirm: " -r
    echo
    if [[ ! $REPLY = "yes" ]]; then
        print_status "Destroy cancelled."
        exit 0
    fi
    
    print_status "Destroying infrastructure with force deletion enabled..."
    print_status "Suppressing verbose synthesis output for cleaner destruction logs..."
    echo ""
    
    cd cdk
    
    # Track destruction status
    local destruction_errors=0
    
    # Destroy frontend first (due to dependencies)
    print_status "🗑️  Destroying frontend stack (ECS, ALB, Streamlit)..."
    if $VERBOSE; then
        cdk destroy ${PROJECT_NAME}-frontend --force --no-rollback --profile $AWS_PROFILE
    else
        cdk destroy ${PROJECT_NAME}-frontend --force --no-rollback --profile $AWS_PROFILE --quiet 2>/dev/null
    fi
    
    if [ $? -eq 0 ]; then
        print_success "✅ Frontend stack destroyed successfully"
    else
        print_error "❌ Frontend stack destruction failed or stack doesn't exist"
        ((destruction_errors++))
    fi
    echo ""
    
    # Destroy backend stack
    print_status "🗑️  Destroying backend stack (RDS, Lambda, API Gateway, S3, DynamoDB)..."
    if $VERBOSE; then
        cdk destroy ${PROJECT_NAME}-backend --force --no-rollback --profile $AWS_PROFILE
    else
        cdk destroy ${PROJECT_NAME}-backend --force --no-rollback --profile $AWS_PROFILE --quiet 2>/dev/null
    fi
    
    if [ $? -eq 0 ]; then
        print_success "✅ Backend stack destroyed successfully"
    else
        print_error "❌ Backend stack destruction failed or stack doesn't exist"
        ((destruction_errors++))
    fi
    echo ""
    
    # Destroy VPC endpoints stack
    print_status "🗑️  Destroying VPC endpoints stack (SSM, S3, Lambda endpoints)..."
    if $VERBOSE; then
        cdk destroy ${PROJECT_NAME}-vpc-endpoints --force --no-rollback --profile $AWS_PROFILE
    else
        cdk destroy ${PROJECT_NAME}-vpc-endpoints --force --no-rollback --profile $AWS_PROFILE --quiet 2>/dev/null
    fi
    
    if [ $? -eq 0 ]; then
        print_success "✅ VPC endpoints stack destroyed successfully"
    else
        print_error "❌ VPC endpoints stack destruction failed or stack doesn't exist"
        ((destruction_errors++))
    fi
    echo ""
    
    # Final status report
    if [ $destruction_errors -eq 0 ]; then
        print_success "🎉 All infrastructure destroyed successfully!"
        print_status "All AWS resources have been removed."
    elif [ $destruction_errors -lt 3 ]; then
        print_warning "⚠️  Partial destruction completed with $destruction_errors error(s)."
        print_warning "Some stacks may not have existed or had dependency issues."
        print_status "Check AWS CloudFormation console for any remaining resources."
    else
        print_error "❌ Destruction completed with multiple errors."
        print_error "Most stacks may not have existed or had issues."
        print_status "Check AWS CloudFormation console for current status."
    fi
    
    echo ""
    print_status "💡 To verify complete cleanup, run: ./deploy.sh status"
    print_status "💡 Use -v/--verbose flag to see detailed destruction output"
}

# Function to check deployment status
check_status() {
    print_status "Checking deployment status..."
    
    check_aws_configured
    
    # Check VPC endpoints stack
    VPC_ENDPOINTS_STATUS=$(aws cloudformation describe-stacks \
        --stack-name "${PROJECT_NAME}-vpc-endpoints" \
        --profile $AWS_PROFILE --region $AWS_REGION \
        --query "Stacks[0].StackStatus" \
        --output text 2>/dev/null || echo "NOT_FOUND")
    
    # Check backend stack
    BACKEND_STATUS=$(aws cloudformation describe-stacks \
        --stack-name "${PROJECT_NAME}-backend" \
        --profile $AWS_PROFILE --region $AWS_REGION \
        --query "Stacks[0].StackStatus" \
        --output text 2>/dev/null || echo "NOT_FOUND")
    
    # Check frontend stack
    FRONTEND_STATUS=$(aws cloudformation describe-stacks \
        --stack-name "${PROJECT_NAME}-frontend" \
        --profile $AWS_PROFILE --region $AWS_REGION \
        --query "Stacks[0].StackStatus" \
        --output text 2>/dev/null || echo "NOT_FOUND")
    
    echo ""
    echo "===================== DEPLOYMENT STATUS ====================="
    echo "Region:              $AWS_REGION"
    echo "VPC Endpoints Stack: $VPC_ENDPOINTS_STATUS"
    echo "Backend Stack:       $BACKEND_STATUS"
    echo "Frontend Stack:      $FRONTEND_STATUS"
    echo "============================================================="
    echo ""
    
    if [ "$VPC_ENDPOINTS_STATUS" = "CREATE_COMPLETE" ] && [ "$BACKEND_STATUS" = "CREATE_COMPLETE" ] && [ "$FRONTEND_STATUS" = "CREATE_COMPLETE" ]; then
        print_success "✅ All stacks are deployed and healthy!"
        echo ""
        print_status "🌐 Access your application:"
        print_status "Run './ssh_tunnel.sh' for detailed access instructions"
    elif [ "$VPC_ENDPOINTS_STATUS" = "NOT_FOUND" ] && [ "$BACKEND_STATUS" = "NOT_FOUND" ] && [ "$FRONTEND_STATUS" = "NOT_FOUND" ]; then
        print_warning "❌ No stacks found. Run './deploy.sh deploy' to create infrastructure."
    else
        print_warning "⚠️  Some stacks may be in progress or have issues."
        print_status "Check AWS CloudFormation console for details."
        
        if $VERBOSE; then
            echo ""
            print_status "Stack details:"
            if [ "$VPC_ENDPOINTS_STATUS" != "NOT_FOUND" ]; then
                aws cloudformation describe-stacks --stack-name "${PROJECT_NAME}-vpc-endpoints" --profile $AWS_PROFILE --region $AWS_REGION --query "Stacks[0].[StackStatus,StackStatusReason]" --output table
            fi
            if [ "$BACKEND_STATUS" != "NOT_FOUND" ]; then
                aws cloudformation describe-stacks --stack-name "${PROJECT_NAME}-backend" --profile $AWS_PROFILE --region $AWS_REGION --query "Stacks[0].[StackStatus,StackStatusReason]" --output table
            fi
            if [ "$FRONTEND_STATUS" != "NOT_FOUND" ]; then
                aws cloudformation describe-stacks --stack-name "${PROJECT_NAME}-frontend" --profile $AWS_PROFILE --region $AWS_REGION --query "Stacks[0].[StackStatus,StackStatusReason]" --output table
            fi
        fi
    fi
}

# Function to clean up build artifacts
cleanup_artifacts() {
    print_status "Cleaning up build artifacts and temporary files..."
    
    if [ -d "cdk/cdk.out" ]; then
        rm -rf cdk/cdk.out
        print_status "Removed cdk.out directory"
    fi
    
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -name "*.pyc" -delete 2>/dev/null || true
    print_status "Removed Python cache files"
    
    if [ -d "node_modules" ]; then
        rm -rf node_modules
        print_status "Removed node_modules directory"
    fi
    
    find . -name ".DS_Store" -delete 2>/dev/null || true
    
    if [ -f "layers/data-analyst-custom-layer.zip" ]; then
        rm layers/data-analyst-custom-layer.zip
        print_status "Removed data-analyst-custom-layer.zip"
    fi
    
    if [ -f "layers/querybot-custom-layer.zip" ]; then
        rm layers/querybot-custom-layer.zip
        print_status "Removed querybot-custom-layer.zip"
    fi
    
    print_success "Cleanup completed successfully!"
}

# Execute the specified command
case $COMMAND in
    validate)
        check_aws_configured
        validate_configuration
        ;;
    bootstrap)
        bootstrap_cdk
        ;;
    deploy)
        deploy_infrastructure
        ;;
    destroy)
        destroy_infrastructure
        ;;
    redeploy)
        redeploy_infrastructure
        ;;
    status)
        check_status
        ;;
    build-layers)
        build_custom_layers
        ;;
    cleanup)
        cleanup_artifacts
        ;;
    *)
        print_error "Unknown command: $COMMAND"
        show_usage
        exit 1
        ;;
esac

print_success "Operation '$COMMAND' completed successfully! 🎉"