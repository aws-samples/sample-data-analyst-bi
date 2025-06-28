"""The file contains various parameters required in the end to end workflow for usecases where data from databases are required for analysis
"""
import os
import streamlit as st
import boto3
from botocore.exceptions import ClientError
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_api_key_from_parameter_store():
    """Retrieve API key from AWS Parameter Store and API Gateway"""
    project_name = os.getenv('PROJECT_NAME', 'data-analyst')
    
    # Use the dynamic parameter name from environment variable if available
    api_key_id_parameter_name = os.getenv('API_KEY_ID_PARAMETER_NAME', f"/{project_name}/api-key-id")
    api_key_value_parameter_name = os.getenv("API_KEY_PARAMETER_NAME", f"/{project_name}/api-key")
    
    print(f"🔑 API Key retrieval started...")
    print(f"📝 Project name: {project_name}")
    print(f"📝 API_KEY_ID parameter: {api_key_id_parameter_name}")
    print(f"📝 API_KEY_VALUE parameter: {api_key_value_parameter_name}")
    
    try:
        # Create AWS clients
        ssm_client = boto3.client('ssm')
        apigateway_client = boto3.client('apigateway')
        
        # Strategy 1: Try to get API key ID and then fetch value from API Gateway
        try:
            print(f"🔍 Attempting to retrieve API key ID: {api_key_id_parameter_name}")
            response = ssm_client.get_parameter(
                Name=api_key_id_parameter_name,
                WithDecryption=False
            )
            api_key_id = response['Parameter']['Value']
            print(f"✅ Retrieved API key ID from Parameter Store: {api_key_id}")
            
            # Get the actual API key value from API Gateway
            api_key_response = apigateway_client.get_api_key(
                apiKey=api_key_id,
                includeValue=True
            )
            api_key_value = api_key_response['value']
            print(f"✅ Successfully retrieved API key value from API Gateway")
            print(f"🔑 API key length: {len(api_key_value)} characters")
            print(f"🔑 API key preview: {api_key_value[:8]}..." if len(api_key_value) > 8 else "🔑 API key too short")
            
            st.success(f"✅ Successfully retrieved API key from API Gateway using ID: {api_key_id}")
            return api_key_value
            
        except ClientError as id_error:
            if id_error.response['Error']['Code'] == 'ParameterNotFound':
                print(f"⚠️ API key ID parameter not found: {id_error}")
            else:
                print(f"⚠️ Error getting API key ID: {id_error}")
        except Exception as api_error:
            print(f"⚠️ Error getting API key from API Gateway: {api_error}")
        
        # Strategy 2: Try to get API key value directly from Parameter Store
        print(f"🔄 Falling back to Parameter Store value...")
        try:
            response = ssm_client.get_parameter(
                Name=api_key_value_parameter_name,
                WithDecryption=True
            )
            api_key_value = response['Parameter']['Value']
            print(f"✅ Retrieved API key value from Parameter Store")
            print(f"🔑 API key length: {len(api_key_value)} characters")
            print(f"🔑 API key preview: {api_key_value[:8]}..." if len(api_key_value) > 8 else "🔑 API key too short")
            
            st.info(f"ℹ️ Using API key from Parameter Store. If you get 403 errors, the API key might be out of sync.")
            return api_key_value
            
        except ClientError as value_error:
            if value_error.response['Error']['Code'] == 'ParameterNotFound':
                print(f"❌ API key value parameter not found: {value_error}")
                st.error(f"❌ API key parameter '{api_key_value_parameter_name}' not found in Parameter Store")
            else:
                print(f"❌ Error getting API key value: {value_error}")
                st.error(f"❌ AWS error retrieving API key: {value_error}")
        
        # Strategy 3: Try to list API keys and get the data-analyst one
        print(f"🔄 Attempting to find API key by name...")
        try:
            api_keys_response = apigateway_client.get_api_keys(
                nameQuery='data-analyst',
                includeValues=True
            )
            
            if api_keys_response['items']:
                # Find the data-analyst API key
                for api_key in api_keys_response['items']:
                    if 'data-analyst' in api_key.get('name', ''):
                        api_key_value = api_key['value']
                        print(f"✅ Found API key by name: {api_key['name']}")
                        print(f"🔑 API key length: {len(api_key_value)} characters")
                        print(f"🔑 API key preview: {api_key_value[:8]}..." if len(api_key_value) > 8 else "🔑 API key too short")
                        
                        st.success(f"✅ Found API key by searching: {api_key['name']}")
                        return api_key_value
                        
                print(f"❌ No data-analyst API key found in {len(api_keys_response['items'])} keys")
            else:
                print(f"❌ No API keys found")
                
        except Exception as search_error:
            print(f"❌ Error searching for API keys: {search_error}")
        
        # All strategies failed
        print(f"❌ All API key retrieval strategies failed")
        st.error("❌ Could not retrieve API key from any source. Please check your AWS configuration.")
        return ""
        
    except Exception as e:
        print(f"❌ Unexpected error in API key retrieval: {e}")
        st.error(f"❌ Unexpected error retrieving API key: {e}")
        return ""


# API Configuration - Require API_ENDPOINT environment variable, no fallback
API_ENDPOINT_ENV = os.getenv("API_ENDPOINT")

if not API_ENDPOINT_ENV:
    logging.error("❌ CRITICAL: API_ENDPOINT environment variable is not set!")
    logging.error("   Expected format: https://<api-id>.execute-api.<region>.amazonaws.com/prod/")
    print("❌ CRITICAL: API_ENDPOINT environment variable is not set!")
    print("   Expected format: https://<api-id>.execute-api.<region>.amazonaws.com/prod/")
    print("   This should be set by the ECS task definition from the backend stack API Gateway URL")
    API_URL = None
else:
    API_URL = API_ENDPOINT_ENV
    print(f"✅ API_ENDPOINT configured: {API_URL}")

# Validate API_URL format if it exists
if API_URL:
    if not API_URL.startswith("https://") or "execute-api" not in API_URL:
        logging.warning(f"⚠️  API_URL format looks incorrect: {API_URL}")
        logging.warning("   Expected format: https://<api-id>.execute-api.<region>.amazonaws.com/prod/")
        print(f"⚠️  API_URL format looks incorrect: {API_URL}")
        print("   Expected format: https://<api-id>.execute-api.<region>.amazonaws.com/prod/")

# Get API key from Parameter Store
API_KEY = get_api_key_from_parameter_store()

# API Database Configuration (for the data analysis queries sent to the API)
API_DB_CONFIG = {
    "host": os.getenv("API_DB_HOST", ""),
    "port": int(os.getenv("API_DB_PORT", "")),
    "database": os.getenv("API_DB_NAME", ""),
    "user": os.getenv("API_DB_USER", ""),
    "password": os.getenv("API_DB_PASSWORD", ""),
    "type": os.getenv("API_DB_TYPE", "")
}

# Metadata Configuration - Use environment variables or fallback to hardcoded values
METADATA_CONFIG = {
    "s3_bucket_name": os.getenv("METADATA_S3_BUCKET", ""),
    "is_meta": os.getenv("METADATA_IS_META", "true").lower() == "true",
    "table_meta": os.getenv("METADATA_TABLE_META", None),
    "column_meta": os.getenv("METADATA_COLUMN_META", None),
    "metric_meta": os.getenv("METADATA_METRIC_META", None),
    "table_access": os.getenv("METADATA_TABLE_ACCESS", None)
}

# Legacy Database Configuration (for backward compatibility)
# This is now replaced by API_DB_CONFIG for API payloads
DB_CONFIG = API_DB_CONFIG

# Legacy configurations for backward compatibility
SQLITE_CONFIG = {
    "database": "data/student_club.db",
    "type": "sqlite"
}

MYSQL_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "database": "student_club",
    "user": "root",
    "password": "password",
    "type": "mysql"
}

POSTGRES_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "student_club",
    "user": "postgres",
    "password": "password",
    "type": "postgresql"
}

# Use the API database configuration as the active config for API payloads
ACTIVE_DB_CONFIG = API_DB_CONFIG

# The types of queries a user can ask
QUERY_TYPES = ["aggregation", "reasoning"]

############################################## 
# Legacy metadata for SQL gen (use METADATA_CONFIG instead)
metadata = METADATA_CONFIG

# Model_ID for generating SQL
model_id = os.getenv("SQL_MODEL_ID", "us.anthropic.claude-3-5-sonnet-20241022-v2:0")

#  Model ID for conversational responses
chat_model_id = os.getenv("CHAT_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")

# Model ID for converting tabular data to natural language responses
expl_model_id = os.getenv("EXPL_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")

# Model ID for generating python query for plotting
plot_model_id = os.getenv("PLOT_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0")

# Embedding Model ID for vector operations
embedding_model_id = os.getenv("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")

# Prompt strategy for SQL gen
sql_gen_approach = os.getenv("APPROACH", "few_shot")  # few_shot, zero_shot, auto

# Cache threshold for selecting entries from a cache database
cache_thresh = os.getenv("CACHE_THRESHOLD", 0.95)  # floating point values (0,1)

# Determines whether tables are to be filtered based on a question,
table_selection = "all" ## values = ["all", "relevant"]  Default - "all" means all tables are to be used

# Whether the chat history is saved in 'S3' or 'local'
chat_save = 'local'

CHAT_S3 = 'data-analysts-deploy-memory-bucket' 

HOME_DIR = r'C:\Users\pansaile\Desktop\Data_Analyst\Streamlit'

DATA_DIR = os.path.join(HOME_DIR, 'db_data')

CHAT_DIR_LOCAL = os.path.join(DATA_DIR, 'chat_out')

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CHAT_DIR_LOCAL, exist_ok=True)

# Number of interactions to keep in the chat history for answer generation
context_hist_size = 5

# Number of interactions to keep in the chat history for plot generation
context_plot_hist_size = 3

# Metadata for SQL generation
METADATA = {
    "students": {
        "description": "Table containing student information",
        "columns": {
            "student_id": "Primary key, unique identifier for each student",
            "first_name": "Student's first name",
            "last_name": "Student's last name",
            "email": "Student's email address",
            "phone": "Student's phone number",
            "date_of_birth": "Student's date of birth",
            "enrollment_date": "Date when student enrolled",
            "graduation_date": "Expected or actual graduation date",
            "gpa": "Grade Point Average",
            "major": "Student's major field of study",
            "year": "Academic year (Freshman, Sophomore, Junior, Senior)",
            "status": "Enrollment status (Active, Inactive, Graduated)"
        }
    },
    "clubs": {
        "description": "Table containing club information",
        "columns": {
            "club_id": "Primary key, unique identifier for each club",
            "club_name": "Name of the club",
            "description": "Description of the club's purpose and activities",
            "founded_date": "Date when the club was founded",
            "category": "Category of the club (Academic, Sports, Cultural, etc.)",
            "meeting_day": "Regular meeting day of the week",
            "meeting_time": "Regular meeting time",
            "meeting_location": "Regular meeting location",
            "advisor_name": "Name of the faculty advisor",
            "advisor_email": "Email of the faculty advisor",
            "max_members": "Maximum number of members allowed",
            "current_members": "Current number of active members",
            "status": "Club status (Active, Inactive, Suspended)"
        }
    },
    "memberships": {
        "description": "Table containing student club membership information",
        "columns": {
            "membership_id": "Primary key, unique identifier for each membership",
            "student_id": "Foreign key referencing students table",
            "club_id": "Foreign key referencing clubs table",
            "join_date": "Date when student joined the club",
            "role": "Student's role in the club (Member, Officer, President, etc.)",
            "status": "Membership status (Active, Inactive, Resigned)"
        }
    },
    "events": {
        "description": "Table containing club events information",
        "columns": {
            "event_id": "Primary key, unique identifier for each event",
            "club_id": "Foreign key referencing clubs table",
            "event_name": "Name of the event",
            "description": "Description of the event",
            "event_date": "Date of the event",
            "start_time": "Start time of the event",
            "end_time": "End time of the event",
            "location": "Event location",
            "max_attendees": "Maximum number of attendees allowed",
            "registration_deadline": "Deadline for event registration",
            "cost": "Cost to attend the event",
            "status": "Event status (Scheduled, Completed, Cancelled)"
        }
    },
    "event_attendance": {
        "description": "Table containing event attendance information",
        "columns": {
            "attendance_id": "Primary key, unique identifier for each attendance record",
            "event_id": "Foreign key referencing events table",
            "student_id": "Foreign key referencing students table",
            "registration_date": "Date when student registered for the event",
            "attendance_status": "Whether student attended (Registered, Attended, No-show)"
        }
    }
}

# Chat history configuration
CHAT_HISTORY_CONFIG = {
    "max_messages": 50,
    "session_timeout": 3600,  # 1 hour in seconds
    "auto_save": True
}





