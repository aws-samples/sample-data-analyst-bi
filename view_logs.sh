#!/bin/bash

# Data Analyst Platform Log Viewer
# View logs from all components with short, descriptive names

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
AWS_PROFILE=""
LINES=50

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

# Usage information
show_usage() {
    echo "Usage: $0 [COMPONENT] [OPTIONS]"
    echo "View logs from Data Analyst platform components."
    echo ""
    echo "Components:"
    echo "  streamlit        View Streamlit UI logs (/data-analyst-streamlit-ui)"
    echo "  api-gateway      View API Gateway logs (/data-analyst-api-gateway)"
    echo "  lambda-querybot  View Querybot Lambda logs (/aws/lambda/data-analyst-querybot)"
    echo "  lambda-data-analyst  View Data Analyst Lambda logs (/aws/lambda/data-analyst-data-analyst)"
    echo "  step-functions   View Step Functions logs (/aws/states/data-analyst-data-processing)"
    echo "  sf-executions    View Step Functions execution history and details"
    echo "  lambda-unzip     View Unzip Lambda logs (/aws/lambda/data-analyst-unzip)"
    echo "  lambda-process   View Process Data Lambda logs (/aws/lambda/data-analyst-process-data)"
    echo "  lambda-upload    View Upload Lambda logs (/aws/lambda/data-analyst-upload)"
    echo "  lambda-complete  View Complete Upload Lambda logs (/aws/lambda/data-analyst-complete-upload)"
    echo "  lambda-projects  View List Projects Lambda logs (/aws/lambda/data-analyst-list-projects)"
    echo "  all              Show all available log groups"
    echo ""
    echo "Options:"
    echo "  -p, --profile PROFILE    AWS profile to use (required)"
    echo "  -l, --lines NUMBER       Number of log lines to display (default: $LINES)"
    echo "  -f, --follow             Follow log output (tail -f behavior)"
    echo "  -s, --start-time TIME    Start time (e.g., '2h' for 2 hours ago)"
    echo "  -h, --help               Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 streamlit -p default                    # View last $LINES lines of Streamlit logs"
    echo "  $0 api-gateway -p default -f               # Follow API Gateway logs in real-time"
    echo "  $0 lambda-data-analyst -p default -l 100   # View last 100 lines of Data Analyst Lambda"
    echo "  $0 step-functions -p default -s 1h         # View Step Functions logs from last hour"
    echo "  $0 sf-executions -p default                # View Step Functions execution history"
    echo "  $0 all -p default                          # List all log groups and their status"
    echo ""
    echo "  # Using environment variable:"
    echo "  export AWS_PROFILE=default && $0 streamlit"
    echo "  export AWS_PROFILE=default && $0 api-gateway -f"
}

# Log group definitions with project name prefix and descriptive names
PROJECT_NAME="data-analyst"
LOG_GROUPS=(
    "/${PROJECT_NAME}-streamlit-ui"
    "/${PROJECT_NAME}-api-gateway" 
    "/aws/lambda/${PROJECT_NAME}-querybot"
    "/aws/lambda/${PROJECT_NAME}-data-analyst"
    "/aws/states/${PROJECT_NAME}-data-processing"
    "/aws/lambda/${PROJECT_NAME}-unzip"
    "/aws/lambda/${PROJECT_NAME}-process-data"
    "/aws/lambda/${PROJECT_NAME}-upload"
    "/aws/lambda/${PROJECT_NAME}-complete-upload"
    "/aws/lambda/${PROJECT_NAME}-list-projects"
)

LOG_DESCRIPTIONS=(
    "Streamlit UI Application"
    "API Gateway Access Logs"
    "Querybot Lambda Function"
    "Data Analyst Lambda Function"
    "Step Functions State Machine"
    "Unzip Lambda Function"
    "Process Data Lambda Function"
    "Upload Lambda Function"
    "Complete Upload Lambda Function"
    "List Projects Lambda Function"
)

# Function to check if log group exists
check_log_group_exists() {
    local log_group=$1
    if aws logs describe-log-groups --log-group-name-prefix "$log_group" --profile "$AWS_PROFILE" --query "logGroups[?logGroupName=='$log_group']" --output text | grep -q "$log_group"; then
        return 0
    else
        return 1
    fi
}

# Function to check if Step Functions state machine exists
check_state_machine_exists() {
    local state_machine_name="${PROJECT_NAME}-data-processing"
    if aws stepfunctions list-state-machines --profile "$AWS_PROFILE" --query "stateMachines[?name=='$state_machine_name'].stateMachineArn" --output text | grep -q "arn:aws:states"; then
        return 0
    else
        return 1
    fi
}

# Function to view Step Functions execution history
view_step_functions_executions() {
    local state_machine_name="${PROJECT_NAME}-data-processing"
    
    print_status "Viewing Step Functions execution history for: $state_machine_name"
    
    if ! check_state_machine_exists; then
        print_warning "Step Functions state machine '$state_machine_name' does not exist or is not accessible"
        print_status "This may mean the Step Functions workflow is not deployed yet"
        return 1
    fi
    
    # Get state machine ARN
    local state_machine_arn=$(aws stepfunctions list-state-machines --profile "$AWS_PROFILE" --query "stateMachines[?name=='$state_machine_name'].stateMachineArn" --output text)
    
    print_status "State Machine ARN: $state_machine_arn"
    echo ""
    
    # List recent executions
    print_status "Recent executions (last 10):"
    aws stepfunctions list-executions \
        --state-machine-arn "$state_machine_arn" \
        --profile "$AWS_PROFILE" \
        --max-items 10 \
        --query 'executions[*].[name,status,startDate,stopDate]' \
        --output table
    
    echo ""
    print_status "Execution details for the most recent execution:"
    
    # Get the most recent execution
    local recent_execution=$(aws stepfunctions list-executions \
        --state-machine-arn "$state_machine_arn" \
        --profile "$AWS_PROFILE" \
        --max-items 1 \
        --query 'executions[0].executionArn' \
        --output text)
    
    if [ "$recent_execution" != "None" ] && [ -n "$recent_execution" ]; then
        print_status "Most recent execution ARN: $recent_execution"
        echo ""
        
        # Get execution history
        print_status "Execution history:"
        aws stepfunctions get-execution-history \
            --execution-arn "$recent_execution" \
            --profile "$AWS_PROFILE" \
            --query 'events[*].[timestamp,type,stateEnteredEventDetails.name,stateExitedEventDetails.name,taskFailedEventDetails.error,taskFailedEventDetails.cause]' \
            --output table
    else
        print_warning "No executions found for this state machine"
    fi
    
    echo ""
    print_status "To view logs for a specific execution, use:"
    echo "  aws stepfunctions describe-execution --execution-arn <EXECUTION_ARN> --profile $AWS_PROFILE"
    echo "  aws stepfunctions get-execution-history --execution-arn <EXECUTION_ARN> --profile $AWS_PROFILE"
}

# Function to view logs for a specific component
view_component_logs() {
    local component=$1
    local log_group=""
    local description=""
    
    case $component in
        streamlit)
            log_group="/${PROJECT_NAME}-streamlit-ui"
            description="Streamlit UI Application"
            ;;
        api-gateway)
            log_group="/${PROJECT_NAME}-api-gateway"
            description="API Gateway Access Logs"
            ;;
        lambda-querybot)
            log_group="/aws/lambda/${PROJECT_NAME}-querybot"
            description="Querybot Lambda Function"
            ;;
        lambda-data-analyst)
            log_group="/aws/lambda/${PROJECT_NAME}-data-analyst"
            description="Data Analyst Lambda Function"
            ;;
        step-functions)
            log_group="/aws/states/${PROJECT_NAME}-data-processing"
            description="Step Functions State Machine"
            ;;
        lambda-unzip)
            log_group="/aws/lambda/${PROJECT_NAME}-unzip"
            description="Unzip Lambda Function"
            ;;
        lambda-process)
            log_group="/aws/lambda/${PROJECT_NAME}-process-data"
            description="Process Data Lambda Function"
            ;;
        lambda-upload)
            log_group="/aws/lambda/${PROJECT_NAME}-upload"
            description="Upload Lambda Function"
            ;;
        lambda-complete)
            log_group="/aws/lambda/${PROJECT_NAME}-complete-upload"
            description="Complete Upload Lambda Function"
            ;;
        lambda-projects)
            log_group="/aws/lambda/${PROJECT_NAME}-list-projects"
            description="List Projects Lambda Function"
            ;;
        sf-executions)
            view_step_functions_executions
            return $?
            ;;
        *)
            print_error "Unknown component: $component"
            show_usage
            exit 1
            ;;
    esac
    
    print_status "Viewing logs for: $description"
    print_status "Log Group: $log_group"
    
    if ! check_log_group_exists "$log_group"; then
        print_warning "Log group '$log_group' does not exist or is not accessible"
        print_status "This may mean the component is not deployed yet"
        return 1
    fi
    
    # Build the AWS CLI command
    local cmd="aws logs tail $log_group --profile $AWS_PROFILE"
    
    if [ "$FOLLOW" = true ]; then
        cmd="$cmd --follow"
        print_status "Following logs in real-time (Ctrl+C to stop)..."
    else
        cmd="$cmd --since $START_TIME"
        print_status "Showing last $LINES lines from $START_TIME..."
    fi
    
    echo ""
    print_status "Command: $cmd"
    echo ""
    
    # Execute the command
    eval "$cmd"
}

# Function to list all log groups
list_all_log_groups() {
    print_status "Data Analyst Platform Log Groups:"
    echo ""
    
    for i in "${!LOG_GROUPS[@]}"; do
        local log_group="${LOG_GROUPS[$i]}"
        local description="${LOG_DESCRIPTIONS[$i]}"
        
        printf "%-40s | %-35s | " "$log_group" "$description"
        
        if check_log_group_exists "$log_group"; then
            printf "${GREEN}✓ Available${NC}\n"
        else
            printf "${RED}✗ Not Found${NC}\n"
        fi
    done
    
    echo ""
    print_status "Step Functions State Machine:"
    printf "%-40s | %-35s | " "${PROJECT_NAME}-data-processing" "Step Functions State Machine"
    if check_state_machine_exists; then
        printf "${GREEN}✓ Available${NC}\n"
    else
        printf "${RED}✗ Not Found${NC}\n"
    fi
    
    echo ""
    print_status "Additional AWS-managed log groups:"
    echo "  API-Gateway-Execution-Logs_*     | API Gateway execution logs (auto-created by AWS)"
    echo ""
    print_status "Quick commands:"
    echo "  ./view_logs.sh streamlit -p default         # View Streamlit UI logs"
    echo "  ./view_logs.sh api-gateway -p default       # View API Gateway logs"
    echo "  ./view_logs.sh lambda-querybot -p default   # View Querybot Lambda logs"
    echo "  ./view_logs.sh lambda-data-analyst -p default    # View Data Analyst Lambda logs"
    echo "  ./view_logs.sh step-functions -p default    # View Step Functions CloudWatch logs"
    echo "  ./view_logs.sh sf-executions -p default     # View Step Functions execution history"
    echo "  ./view_logs.sh lambda-unzip -p default      # View Unzip Lambda logs"
    echo "  ./view_logs.sh lambda-process -p default    # View Process Data Lambda logs"
    echo "  ./view_logs.sh lambda-upload -p default     # View Upload Lambda logs"
    echo "  ./view_logs.sh lambda-complete -p default   # View Complete Upload Lambda logs"
    echo "  ./view_logs.sh lambda-projects -p default   # View List Projects Lambda logs"
}

# Parse arguments
COMPONENT=""
FOLLOW=false
START_TIME="1h"

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
        -l|--lines)
            LINES="$2"
            START_TIME="${LINES} lines"
            shift 2
            ;;
        -f|--follow)
            FOLLOW=true
            shift
            ;;
        -s|--start-time)
            START_TIME="$2"
            shift 2
            ;;
        streamlit|api-gateway|lambda-querybot|lambda-data-analyst|step-functions|sf-executions|lambda-unzip|lambda-process|lambda-upload|lambda-complete|lambda-projects|all)
            COMPONENT="$1"
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Validate AWS_PROFILE is set (either from command line or environment variable)
if [ -z "$AWS_PROFILE" ]; then
    print_error "AWS_PROFILE is not set!"
    print_error ""
    print_error "Please set the AWS profile using one of these methods:"
    print_error "  1. Set environment variable: export AWS_PROFILE=your-profile-name"
    print_error "  2. Use the -p option: $0 COMPONENT -p your-profile-name"
    print_error ""
    print_error "Examples:"
    print_error "  export AWS_PROFILE=default && $0 streamlit"
    print_error "  $0 streamlit -p default"
    print_error "  $0 api-gateway -p default"
    print_error ""
    print_error "To list available AWS profiles, run: aws configure list-profiles"
    exit 1
fi

if [ -z "$COMPONENT" ]; then
    print_error "No component specified"
    show_usage
    exit 1
fi

# Export AWS profile
export AWS_PROFILE=$AWS_PROFILE

print_status "Using AWS profile: $AWS_PROFILE"

# Check if AWS CLI is configured
if ! aws sts get-caller-identity --profile $AWS_PROFILE &> /dev/null; then
    print_error "AWS CLI not configured for profile '$AWS_PROFILE'"
    print_error "Run: aws configure --profile $AWS_PROFILE"
    exit 1
fi

# Execute the requested action
case $COMPONENT in
    all)
        list_all_log_groups
        ;;
    *)
        view_component_logs "$COMPONENT"
        ;;
esac 