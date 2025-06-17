#!/bin/bash

# SSH Tunnel to Streamlit Application
# Creates a secure tunnel to access the internal Streamlit app from your local browser

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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
AWS_PROFILE=""
LOCAL_PORT="8080"
TEMP_KEY_PATH="/tmp/ssm_tunnel_key"

# Usage information
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Create SSH tunnel to access Streamlit application from local browser."
    echo ""
    echo "Options:"
    echo "  -h, --help                Show this help message"
    echo "  -p, --profile PROFILE     AWS profile to use (required)"
    echo "  -n, --project-name NAME   Project name (default: $PROJECT_NAME)"
    echo "  -l, --local-port PORT     Local port for tunnel (default: $LOCAL_PORT)"
    echo ""
    echo "Examples:"
    echo "  $0 -p default             # Use default AWS profile"
    echo "  $0 -p default -l 8081     # Use port 8081 instead of 8080"
    echo ""
    echo "After running this script, open: http://localhost:$LOCAL_PORT"
}

# Parse arguments
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
        -n|--project-name)
            PROJECT_NAME="$2"
            shift 2
            ;;
        -l|--local-port)
            LOCAL_PORT="$2"
            shift 2
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Validate AWS_PROFILE is set
if [ -z "$AWS_PROFILE" ]; then
    print_error "AWS_PROFILE is not set!"
    print_error ""
    print_error "Please set the AWS profile using one of these methods:"
    print_error "  1. Set environment variable: export AWS_PROFILE=your-profile-name"
    print_error "  2. Use the -p option: $0 -p your-profile-name"
    print_error ""
    print_error "Examples:"
    print_error "  export AWS_PROFILE=default && $0"
    print_error "  $0 -p default"
    print_error ""
    print_error "To list available AWS profiles, run: aws configure list-profiles"
    exit 1
fi

export AWS_PROFILE=$AWS_PROFILE

echo "🌐 Setting up SSH tunnel to Streamlit application..."
echo ""
print_status "Project: $PROJECT_NAME"
print_status "AWS Profile: $AWS_PROFILE"
print_status "Local Port: $LOCAL_PORT"
echo ""

# Check AWS CLI configuration
if ! aws sts get-caller-identity --profile $AWS_PROFILE &> /dev/null; then
    print_error "AWS CLI not configured for profile '$AWS_PROFILE'"
    print_error "Run: aws configure --profile $AWS_PROFILE"
    exit 1
fi

# Get bastion instance ID
print_status "Getting bastion instance details..."
BASTION_INSTANCE_ID=$(aws cloudformation describe-stacks \
    --stack-name "${PROJECT_NAME}-frontend" \
    --query "Stacks[0].Outputs[?OutputKey=='BastionHostInstanceId'].OutputValue" \
    --output text --profile $AWS_PROFILE 2>/dev/null || echo "")

if [ -z "$BASTION_INSTANCE_ID" ] || [ "$BASTION_INSTANCE_ID" = "None" ]; then
    print_error "Frontend stack not found or bastion instance not deployed"
    exit 1
fi

# Get internal ALB DNS
INTERNAL_ALB_DNS=$(aws cloudformation describe-stacks \
    --stack-name "${PROJECT_NAME}-frontend" \
    --query "Stacks[0].Outputs[?OutputKey=='StreamlitAppInternalURL'].OutputValue" \
    --output text --profile $AWS_PROFILE 2>/dev/null | sed 's|http://||')

if [ -z "$INTERNAL_ALB_DNS" ]; then
    print_error "Could not retrieve internal ALB DNS name"
    exit 1
fi

# Get availability zone
BASTION_AZ=$(aws ec2 describe-instances \
    --instance-ids $BASTION_INSTANCE_ID \
    --query "Reservations[0].Instances[0].Placement.AvailabilityZone" \
    --output text --profile $AWS_PROFILE)

print_success "✅ Found bastion: $BASTION_INSTANCE_ID"
print_success "✅ Found internal ALB: $INTERNAL_ALB_DNS"
echo ""

# Check if port is already in use
if lsof -Pi :$LOCAL_PORT -sTCP:LISTEN -t >/dev/null ; then
    print_error "Port $LOCAL_PORT is already in use!"
    print_status "Kill the existing process or choose a different port with -l option"
    exit 1
fi

# Clean up any existing temporary keys
if [ -f "$TEMP_KEY_PATH" ]; then
    rm -f "$TEMP_KEY_PATH" "$TEMP_KEY_PATH.pub"
fi

# Generate temporary SSH key pair
print_status "Generating temporary SSH key..."
ssh-keygen -t rsa -f "$TEMP_KEY_PATH" -N '' -q

# Send public key to instance via EC2 Instance Connect
print_status "Sending temporary key to bastion host..."
aws ec2-instance-connect send-ssh-public-key \
    --instance-id $BASTION_INSTANCE_ID \
    --availability-zone $BASTION_AZ \
    --instance-os-user ec2-user \
    --ssh-public-key file://$TEMP_KEY_PATH.pub \
    --profile $AWS_PROFILE

if [ $? -eq 0 ]; then
    print_success "✅ Temporary key sent successfully"
else
    print_error "Failed to send public key to instance"
    rm -f "$TEMP_KEY_PATH" "$TEMP_KEY_PATH.pub"
    exit 1
fi

# Create cleanup function
cleanup() {
    print_status "Cleaning up..."
    if [ -f "$TEMP_KEY_PATH" ]; then
        rm -f "$TEMP_KEY_PATH" "$TEMP_KEY_PATH.pub"
    fi
    print_status "Tunnel closed. Goodbye!"
}

# Set trap to cleanup on exit
trap cleanup EXIT

echo ""
print_success "🚀 Starting SSH tunnel..."
print_warning "⏰ You have 60 seconds from key injection to connect"
print_success "🌐 Open your browser to: http://localhost:$LOCAL_PORT"
print_status "Press Ctrl+C to close the tunnel"
echo ""

# Create the SSH tunnel
ssh -i "$TEMP_KEY_PATH" ec2-user@$BASTION_INSTANCE_ID \
    -L $LOCAL_PORT:$INTERNAL_ALB_DNS:80 \
    -o ProxyCommand="aws ssm start-session --target %h --document-name AWS-StartSSHSession --parameters 'portNumber=%p' --profile $AWS_PROFILE" \
    -o UserKnownHostsFile=/dev/null \
    -o StrictHostKeyChecking=no \
    -N 