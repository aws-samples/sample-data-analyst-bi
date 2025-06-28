import streamlit as st
from datetime import datetime, timezone
import requests
import json
from typing import Dict, List
import os
import re
import boto3
import pandas as pd
import base64
from streamlit.components.v1 import html
from config import ACTIVE_DB_CONFIG, metadata, model_id, chat_model_id, expl_model_id, plot_model_id, embedding_model_id, sql_gen_approach, chat_save, context_hist_size, CHAT_DIR_LOCAL, CHAT_S3, METADATA_CONFIG, API_URL, API_KEY, QUERY_TYPES, cache_thresh, table_selection
from enum import Enum
import uuid
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ModelNames(str, Enum):
    CLAUDE_V2 = "anthropic.claude-v2:1"
    CLAUDE_INSTANT = "anthropic.claude-instant-v1"
    CLAUDE_3_SONNET = "anthropic.claude-3-sonnet-20240229-v1:0"
    CLAUDE_3_5_SONNET_V1 = "anthropic.claude-3-5-sonnet-20240620-v1:0"
    CLAUDE_3_5_SONNET_V2 = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
    CLAUDE_3_7_SONNET_V1 = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
    CLAUDE_3_HAIKU = "anthropic.claude-3-haiku-20240307-v1:0"
    CLAUDE_3_5_HAIKU = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
    NOVA_MICRO = "amazon.nova-micro-v1:0"
    NOVA_LITE = "amazon.nova-lite-v1:0"
    NOVA_PRO = "amazon.nova-pro-v1:0",
    LLAMA_3_3_70B = "us.meta.llama3-3-70b-instruct-v1:0"
    TITAN_EMBED_V1 = "amazon.titan-embed-text-v1"
    TITAN_EMBED_V2 = "amazon.titan-embed-text-v2:0"
    COHERE_EMBED_EN = "cohere.embed-english-v3"
    COHERE_EMBED_MULTI = "cohere.embed-multilingual-v3"
    SQL_CODER = "defog/sqlcoder-7b-2"
    DEEPSEEK_R1_70B = "ic-deepseek-r1-distill-llama-70b"
    LLAMA_3_3_70B_SM = "ic-llama-3-3-70b-instruct"

# Page configuration is handled by Home.py - don't call set_page_config here
# This prevents the "set_page_config() can only be called once" error

# Initialize session state variables
    if "questions" not in st.session_state:
        st.session_state.questions = []
    if "answers" not in st.session_state:
        st.session_state.answers = []
    if "query_type" not in st.session_state:
        st.session_state.query_type = ""
    if "question_query_map" not in st.session_state:
        st.session_state.question_query_map = ""
    if "current_user_input" not in st.session_state:
        st.session_state.current_user_input = ""
    if "current_sql" not in st.session_state:
        st.session_state.current_sql = ""
    if "pending_approval" not in st.session_state:
        st.session_state.pending_approval = False
    if 'chat_history_sql' not in st.session_state:
        st.session_state['chat_history_sql'] = []
    if 'text_sql_status' not in st.session_state:
        st.session_state['text_sql_status'] = []
    if 'chat_history_tabs' not in st.session_state:
        st.session_state['chat_history_tabs'] = []
    if "plot_history" not in st.session_state:
        st.session_state.plot_history = []
    if "show_plot_container" not in st.session_state:
        st.session_state.show_plot_container = True
    if 'session_initialized' not in st.session_state:
        st.session_state.session_initialized = False
    if 'info_message' not in st.session_state:
        st.session_state.info_message = None
    if "persona" not in st.session_state:
        st.session_state.persona = "Data Analyst"  # Default value
    if "uid" not in st.session_state:
        st.session_state.uid = str(datetime.now().timestamp())  # Unique session ID
    if "action" not in st.session_state:
        st.session_state.action = None
    if "cached_flag" not in st.session_state:
        st.session_state.cached_flag = None
    if "current_dataframe" not in st.session_state:  # Added for dataframe persistence
        st.session_state.current_dataframe = None

# Sidebar configuration
with st.sidebar:
    st.title("🤖 Data Analyst Platform")
    st.markdown("---")
    
    # Profile Selection - Only Admin available
    st.subheader("👤 User Profile")
    profile_options = ["Admin"]
    
    selected_persona = st.selectbox(
        "Current Role:",
        options=profile_options,
        index=0,  # Always Admin
        help="Administrative access to the data analysis platform.",
        disabled=True  # Disable selection since only one option
    )
    
    # Update session state
    st.session_state['persona'] = selected_persona
    
    st.markdown("---")
    
    # System Information
    st.subheader("📊 System Info")
    st.info(f"**Role:** {st.session_state['persona']}")
    st.info(f"**Session ID:** {st.session_state['uid'][:8]}...")
    
    # API Configuration Status
    st.subheader("🔧 API Configuration")
    if API_URL is None:
        st.error("❌ **API Endpoint:** Not configured")
        st.write("Missing API_ENDPOINT environment variable")
    else:
        st.success("✅ **API Endpoint:** Configured")
        with st.expander("View API URL"):
            st.code(API_URL)
    
    if not API_KEY:
        st.error("❌ **API Key:** Not configured")
        st.write("Missing or failed to retrieve from Parameter Store")
    else:
        st.success("✅ **API Key:** Configured")
        st.write("Retrieved from AWS Parameter Store")
    
    # Quick Actions
    st.subheader("🔧 Quick Actions")
    if st.button("🗑️ Clear Chat History", type="secondary", use_container_width=True):
        st.session_state['chat_history_sql'] = []
        st.session_state['chat_history_tabs'] = []
        st.session_state.questions = []
        st.session_state.answers = []
        st.rerun()
    
    if st.button("🔄 Reset Session", type="secondary", use_container_width=True):
        for key in list(st.session_state.keys()):
            if key not in ['persona']:  # Keep persona
                del st.session_state[key]
        st.rerun()

# comprehensive CSS first for page settings
st.markdown("""
    <style>
        /* Disable main page scrolling */
        .main {
            overflow-y: hidden;
        }
        
        /* Remove padding/margin from main container */
        .block-container {
            padding-top: 1rem;
            padding-bottom: 0rem;
            padding-left: 1rem;
            padding-right: 1rem;
            margin: 0;
        }

        /* Disable horizontal scroll */
        [data-testid="stHorizontalBlock"] {
            overflow-x: hidden;
        }
        
        /* Enable vertical scroll for individual containers */
        [data-testid="stContainer"] {
            overflow-y: auto;
        }

        /* Ensure content fits viewport */
        .stApp {
            height: 100vh;
            overflow: hidden;
        }
    </style>
""", unsafe_allow_html=True)


# Add custom CSS to ensure proper alignment and spacing
st.markdown("""
    <style>
        /* Reduce spacing between subheader and container */
        .stSubheader {
            margin-bottom: 0.5rem;
        }
        
        /* Ensure containers have proper spacing */
        [data-testid="stContainer"] {
            margin-top: 0.5rem;
        }
        
        /* Adjust column gap */
        [data-testid="stHorizontalBlock"] {
            gap: 1rem;
        }
    </style>
""", unsafe_allow_html=True)

s3 = boto3.resource('s3')

# API Configuration - Now using values from config.py
# API_URL and API_KEY are imported from config.py

def render_ui():
    st.title("📊 Data Analysis Dashboard")
    st.markdown("**Welcome to the Data Analyst Platform** - Ask questions about your data and get AI-powered insights")


# function to handle auto-scrolling
def auto_scroll_to_bottom():
    js_code = """
    <script>
        function scroll() {
            var chatContainer = document.querySelector('[data-testid="stVerticalBlock"]');
            if (chatContainer) {
                chatContainer.scrollTop = chatContainer.scrollHeight;
            }
        }
        scroll();
    </script>
    """
    html(js_code)

def trim_history(chat_type):
    """This function to be used to retain only the specified chat history size
    Args:
    chat_type (str): whether the tables are returned or answers are returned(history of question and returned tables are maintained separately than the history of question and answers
    
    Returns:the trimmed history
    """
    if chat_type == 'answer':
        messages = st.session_state['chat_history_sql'][-context_hist_size:]
    elif chat_type == 'table':
        messages = st.session_state['chat_history_tabs'][-context_hist_size:]
    return messages

def clear():
     return ""

def display_chat_history(chat_history):
    """Display chat messages without table data"""
    for msglist in chat_history:
        role = msglist['role']
        msg = msglist['content'][0]["text"]
        # Only display text content, not table data
        if not msg.startswith('|') and not all(c in '|-+ ' for c in msg):  # Skip markdown tables
            st.chat_message(role).markdown(msg)

        
def save_chat_history(chat_history, uid):
    """This function to be used to save the chat history in a json format
    Args:
    chat_history (list) : the history of questions, responses and status
    uid (str): chat history from each session is saved with a unique identifier for the session
    """
    if chat_save == 'local':
        with open(os.path.join(CHAT_DIR_LOCAL, 'text_sql_status_{}.json'.format(uid)), "w", encoding='utf-8') as f:
            json.dump(chat_history, f, ensure_ascii=False, indent=4)
    elif chat_save == 'S3':
        json_data = json.dumps(chat_history, ensure_ascii=False, indent=4)
        # Initialize S3 client
        s3_client = boto3.client('s3')
        # Define bucket name and object key (file path)
        object_key = 'text_sql_status_{}.json'.format(uid)
        # Upload JSON data to S3
        try:
            s3_client.put_object(
                Body=json_data,
                Bucket=CHAT_S3,
                Key=object_key,
                ContentType='application/json'
            )
            print(f"Successfully uploaded JSON data to s3://{CHAT_S3}/{object_key}")
        except Exception as e:
            print(f"Error uploading to S3: {e}")

def add_to_chat_history(question, answer, table):
    """This function to be used to add the questions from user and responses from bot to chat history
    Args:
    question (str): the question from the user
    answer (str): the natural language answer
    table (dict/DataFrame): the dataframe received from the API response (as dict) or None
    
    """
    if question:
        st.session_state['chat_history_sql'].append({"role": "user", "content": [{"text": question}]}) 
        st.session_state['chat_history_tabs'].append({"role": "user", "content": [{"text": question}]}) 
        st.session_state['questions'].append(question)
    if answer:
        st.session_state['chat_history_sql'].append({"role": "assistant", "content": [{"text": answer}]})
    if table is not None:
        # Format table representation
        if isinstance(table, pd.DataFrame):
            table_str = table.to_markdown()  # More readable format
        elif isinstance(table, dict):
            # Convert dict back to DataFrame for better formatting
            temp_df = pd.DataFrame(table)
            table_str = temp_df.to_markdown()
        else:
            table_str = str(table)
        
        st.session_state['chat_history_tabs'].append({"role": "assistant", "content": [{"text": table_str}]})


def send_api_request(user_query: str, query_type: str, user_persona: str, 
                     question_query_map: dict, messages: List[Dict]) -> Dict:
    """Send request to API Gateway"""
    
    # Check if API_URL is properly configured
    if API_URL is None:
        error_msg = {
            'answer': '❌ Configuration Error: API endpoint not configured. Please check that the API_ENDPOINT environment variable is set correctly in the ECS task definition.',
            'error': 'API_ENDPOINT_NOT_CONFIGURED'
        }
        logger.error("API_URL is None - API_ENDPOINT environment variable not set")
        print("❌ API_URL is None - cannot send request")
        return error_msg
    
    # Check if API_KEY is properly configured
    if not API_KEY:
        error_msg = {
            'answer': '❌ Configuration Error: API key not configured. Please check that the API key is properly set in AWS Parameter Store and accessible.',
            'error': 'API_KEY_NOT_CONFIGURED'
        }
        logger.error("API_KEY is empty or None - API key not retrieved from Parameter Store")
        print("❌ API_KEY is empty - cannot send authenticated request")
        return error_msg
    
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": API_KEY
    }
    session_value = 'new' if not st.session_state.session_initialized else 'existing'
    if not st.session_state.session_initialized:
        st.session_state.session_initialized = True
    messages = trim_history(chat_type='answer')
    payload = {
        "user_persona": user_persona,
        "user_query": user_query,
        "question_query_map": question_query_map,
        "sql_model_id": model_id,
        "chat_model_id": chat_model_id,
        "embedding_model_id": embedding_model_id,
        "expl_model_id": expl_model_id,
        "plot_model_id": plot_model_id,
        "approach": sql_gen_approach,
        "table_selection": table_selection,
        "query_type": query_type,
        "cache_thresh": cache_thresh,
        "db_conn_conf": {
            'db_type': ACTIVE_DB_CONFIG['type'],
            'host': ACTIVE_DB_CONFIG['host'],
            'user': ACTIVE_DB_CONFIG['user'],
            'password': ACTIVE_DB_CONFIG['password'],
            'database': ACTIVE_DB_CONFIG['database'],
            'port': ACTIVE_DB_CONFIG['port']
        },
        "metadata": {
            "s3_bucket_name": METADATA_CONFIG["s3_bucket_name"],
            "is_meta": METADATA_CONFIG["is_meta"],
            "table_meta": METADATA_CONFIG["table_meta"],
            "column_meta": METADATA_CONFIG["column_meta"],
            "metric_meta": METADATA_CONFIG["metric_meta"],
            "table_access": METADATA_CONFIG["table_access"]
        },
        "messages": messages,
        "session": session_value
    }



    gmt_time = datetime.now(timezone.utc).isoformat()
    print(f"{gmt_time}\t{st.session_state.persona}\t\t{user_query}")
    
    try:
        # Enhanced logging for debugging
        logger.info(f"📡 Making API request to: {API_URL}")
        logger.info(f"🔑 API Key configured: {bool(API_KEY)} (length: {len(API_KEY) if API_KEY else 0})")
        logger.info(f"📝 Request payload keys: {list(payload.keys())}")
        logger.info(f"🕒 Session type: {session_value}")
        logger.info(f"📊 User query: {user_query}")
        
        print(f"📡 Making API request to: {API_URL}")
        print(f"🔑 Using API key: {API_KEY[:10]}...")  # Show first 10 chars for debugging
        print(f"📝 Payload size: {len(str(payload))} characters")
        
        response = requests.post(API_URL, json=payload, headers=headers, timeout=600)
        # Log response details
        gmt_time = datetime.now(timezone.utc).isoformat()
        
        logger.info(f"📬 Response received - Status: {response.status_code}")
        logger.info(f"📋 Response headers: {dict(response.headers)}")
        
        print(f"{gmt_time}\tResponse Status: {response.status_code}")
        print(f"📋 Response headers: {dict(response.headers)}")
        print(f"📄 Response content type: {response.headers.get('content-type', 'Unknown')}")
        if response.status_code != 200:
            logger.error(f"❌ Non-200 status code: {response.status_code}")
            logger.error(f"❌ Response text: {response.text}")
            print(f"❌ Error response ({response.status_code}): {response.text}")
            return {
                'answer': f'API Error (Status {response.status_code}): {response.text}',
                'error': f'HTTP_{response.status_code}'
            }
    # Try to parse JSON response
        try:
            response_json = response.json()
            logger.info(f"✅ JSON response parsed successfully")
            logger.info(f"📊 Response keys: {list(response_json.keys()) if isinstance(response_json, dict) else 'Not a dict'}")
            print(f"✅ Successful API response with keys: {list(response_json.keys()) if isinstance(response_json, dict) else 'Not a dict'}")
            logger.info(f"{gmt_time}\tResponse: {response_json}")
            return response_json
        except ValueError as json_error:
            logger.error(f"❌ JSON parsing failed: {json_error}")
            logger.error(f"❌ Raw response text: {response.text[:500]}...")  # First 500 chars
            print(f"❌ JSON parsing failed: {json_error}")
            print(f"❌ Raw response (first 200 chars): {response.text[:200]}")
            return {
                'answer': f'JSON Parse Error: Response was not valid JSON. Raw response: {response.text[:200]}...',
                'error': 'JSON_PARSE_ERROR'
            }
            
    except requests.exceptions.Timeout as timeout_error:
        logger.error(f"⏰ Request timeout: {timeout_error}")
        print(f"⏰ Request timeout after 600 seconds: {timeout_error}")
        return {
            'answer': 'Request timed out after 10 minutes. The API might be experiencing high load. Please try again.',
            'error': 'REQUEST_TIMEOUT'
        }
    except requests.exceptions.ConnectionError as conn_error:
        logger.error(f"🔌 Connection error: {conn_error}")
        print(f"🔌 Connection error: {conn_error}")
        return {
            'answer': f'Connection Error: Could not connect to API. Please check your network connection. Error: {conn_error}',
            'error': 'CONNECTION_ERROR'
        }
    except requests.exceptions.HTTPError as http_error:
        logger.error(f"🌐 HTTP error: {http_error}")
        print(f"🌐 HTTP error: {http_error}")
        return {
            'answer': f'HTTP Error: {http_error}',
            'error': 'HTTP_ERROR'
        }
    except requests.exceptions.RequestException as request_error:
        logger.error(f"📡 Request error: {request_error}")
        print(f"📡 General request error: {request_error}")
        # Try to get response text if available
        response_text = "No response text available"
        try:
            if 'response' in locals():
                response_text = response.text
        except:
            pass
        print(f"📄 Response text: {response_text}")
        return {
            'answer': f'Request Error: {request_error}. Response: {response_text}',
            'error': 'REQUEST_ERROR'
        }
    except Exception as unexpected_error:
        logger.error(f"💥 Unexpected error: {unexpected_error}")
        print(f"💥 Unexpected error: {unexpected_error}")
        return {
            'answer': f'Unexpected Error: {unexpected_error}',
            'error': 'UNEXPECTED_ERROR'
        }


if __name__ == "__main__":
    render_ui()

    # Constants
    CHAT_CONTAINER_HEIGHT = 400  # Reduced height for chat container
    TOP_ROW_HEIGHT = 400  # Height for data view and visualization
    CONTAINER_PADDING = 8
    SUBHEADER_HEIGHT = 35
    
    if st.session_state.current_dataframe is not None:
        st.sidebar.write(f"DataFrame Shape: {st.session_state.current_dataframe.shape}")
    
    # Reset button for testing
    if st.sidebar.button("Reset Session"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


    # SQL Approval Section - Moved to the top so it appears first when pending_approval is True
    if st.session_state.pending_approval:
        st.subheader("SQL Review")
        
        approval_container = st.container(border=True)
        with approval_container:
            st.write("Please review the SQL query:")
            st.code(st.session_state.current_sql, language="sql")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Approve SQL", key="approve_button", use_container_width=True):
                    st.session_state.action = "approve"
                    st.session_state.pending_approval = False
                    st.rerun()
            
            with col2:
                if st.button("❌ Reject SQL", key="reject_button", use_container_width=True):
                    st.session_state.action = "reject"
                    st.session_state.pending_approval = False
                    st.rerun()

    # Handle actions after rerun
    if st.session_state.action:
        if st.session_state.action == "approve":
            # Just store the approval status, don't re-execute SQL
            user_input = st.session_state.current_user_input
            sql = st.session_state.current_sql
            query_type = st.session_state.query_type
            response = send_api_request(
                    user_query=user_input,
                    query_type=query_type,
                    user_persona=st.session_state.persona,
                    question_query_map={"question": user_input,"queries": sql},
                    messages=st.session_state['chat_history_sql']
            )
            print("response", response)
            if response["status"] == "successful":
                st.success("SQL Approved and saved!")
                print("response_cache", response)
                st.session_state['text_sql_status'].append({"question": user_input, "sql": sql, "status": "approved"})
            
        elif st.session_state.action == "reject":
            st.warning("SQL Rejected!")
            # Additional handling code for rejected SQL
            user_input = st.session_state.current_user_input
            sql = st.session_state.current_sql
            st.session_state['text_sql_status'].append({"question": user_input, "sql": sql, "status": "rejected"})
        
        # Reset the action state
        st.session_state.action = None

    # Row 1: Data View and Visualization
    row1_col1, row1_col2 = st.columns(2, gap="small")

    with row1_col1:
        st.subheader("📑 Data View")
        data_container = st.container(border=True, height=TOP_ROW_HEIGHT)
        # Always display current dataframe if it exists
        with data_container:
            if st.session_state.current_dataframe is not None:
                st.dataframe(
                    st.session_state.current_dataframe,
                    use_container_width=True,
                    height=TOP_ROW_HEIGHT - 100
                )
                if not st.session_state.current_dataframe.empty:
                    csv = st.session_state.current_dataframe.to_csv(index=False)
                    st.download_button(
                        label="Download data as CSV",
                        data=csv,
                        file_name="query_results.csv",
                        mime="text/csv",
                    )
            else:
                st.write("No data available. Ask a question to get started!")

    with row1_col2:
        st.subheader("📊 Visualization")
        plot_container = st.container(border=True, height=TOP_ROW_HEIGHT)
        if not st.session_state.show_plot_container:
            plot_container = st.empty()
        else:
            with plot_container:
                # Display the stored plot image if it exists
                if 'current_plot_image' in st.session_state and st.session_state.current_plot_image is not None:
                    st.image(st.session_state.current_plot_image, use_column_width=True)
                else:
                    st.write("No visualization available.")

    # Row 2: Chat History (full width)
    st.subheader("💬 Chat History")
    chat_container = st.container(border=True, height=CHAT_CONTAINER_HEIGHT)
    
    # Create info container and display message
    info_container = st.container()
    
    # Chat input at the bottom
    # Adjust the layout for the input area at the bottom
    input_col1, input_col2 = st.columns([1, 4])  # This gives a 1:4 ratio - adjust as needed

    # Put the dropdown in the first (left) column
    with input_col1:
        query_type = st.selectbox(
            "Select Query Type",
            options=QUERY_TYPES,
            label_visibility="collapsed"  # Optional: removes the label for cleaner layout
        )
        st.session_state.query_type = query_type

    # Put the chat input in the second (right) column
    with input_col2:
        user_input = st.chat_input("Ask me questions related to your data")

    # Display chat history
    with chat_container:
        for msglist in st.session_state['chat_history_sql']:
            role = msglist['role']
            msg = msglist['content'][0]["text"]
            
            with st.chat_message(role):
                if 'SELECT' in msg.upper() or 'FROM' in msg.upper():
                    st.code(msg, language='sql')
                elif 'import' in msg.lower() or 'plt.' in msg:
                    st.code(msg, language='python')
                else:
                    st.text(msg)


    if user_input:
        ## Set the plot data to None
        if 'current_plot_image' in st.session_state:
            st.session_state.current_plot_image = None
        auto_scroll_to_bottom()
        st.session_state.current_question = user_input
        # Display user message
        with chat_container:
            st.chat_message("user").markdown(user_input)
            add_to_chat_history(question=user_input, answer=False, table=False)
        # Get API response
        response = send_api_request(
            user_query=st.session_state.current_question,
            query_type=st.session_state.query_type,
            user_persona=st.session_state.persona,
            question_query_map={},
            messages=st.session_state['chat_history_sql']
        )
        if response:
            # Clear the plot image if this is a new query (not during approval flow)
            # Update info message
            if 'cached_flag' in response and response['cached_flag']:
                st.session_state.cached_flag = response['cached_flag']
                print("st.session_state.cached_flag", st.session_state.cached_flag)
                logger.info(f"st.session_state.cached_flag: {st.session_state.cached_flag}")
            
            else:
                # Reset the flag when not present in response
                st.session_state.cached_flag = False
                print("Resetting cached_flag to False")
                logger.info("Resetting cached_flag to False")
            if 'filter_values' in response and response['filter_values']:
                st.session_state.info_message = response['filter_values']
            else:
                st.session_state.info_message = None

            # Update the info container
            with info_container:
                st.empty()
                if st.session_state.info_message:
                    st.info(f"Additional Information: {st.session_state.info_message}", icon="ℹ️")

            # Handle Plotting Query
            if 'plot' in response:
                st.session_state.show_plot_container = True
                plot_data = response.get('plot', '')
                sql = response.get('sql_query', '')
                answer = response.get('answer', '')
                print("sql inside plot", sql)

                # Store the plot data in session state so it persists after rerun
                if plot_data:
                    try:
                        # Decode and store the plot image in session state
                        st.session_state.current_plot_image = base64.b64decode(plot_data)
                    except Exception as e:
                        st.error(f"Error decoding plot: {str(e)}")
                        st.session_state.current_plot_image = None
                with chat_container:
                    with st.chat_message("assistant"):
                        if answer:
                            st.text(answer)
                        if sql:
                            st.code(sql, language='sql')
                    chat_content = []
                    if answer:
                        chat_content.append(answer)
                    if sql:
                        chat_content.append(sql)  # Fixed: was using 'sql' variable which is undefined here
                    add_to_chat_history(question=None, answer="\n".join(chat_content), table=None)
                    logger.info(f"💬 Current Question - {st.session_state.current_question}/n Current Response - {chat_content}")
                if 'dataframe' in response:
                    try:
                        df_data = json.loads(response['dataframe'])
                        df = pd.DataFrame(df_data)
                        
                        for col in df.columns:
                            if df[col].dtype == 'object':
                                try:
                                    df[col] = pd.to_datetime(df[col])
                                except:
                                    pass
                        
                        # Store in session state
                        st.session_state.current_dataframe = df
                        
                    except Exception as e:
                        with chat_container:
                            st.error(f"Error processing dataframe: {str(e)}")
                st.rerun()

            # Handle SQL Query
            elif 'sql_query' in response:
                # Clear any existing plots since this is not a plot query
                if 'current_plot_image' in st.session_state:
                    st.session_state.current_plot_image = None
                answer = response.get('answer', '')
                sql = response.get('sql_query', '')
                st.session_state.current_sql = sql
                if st.session_state.cached_flag != True:
                    st.session_state.pending_approval = True # Set the flag to show approval buttons
                else:
                    st.session_state.pending_approval = False
                st.session_state.current_user_input = user_input  # Store the current user input
                st.info(f"cache status: {st.session_state.cached_flag}", icon="ℹ️")
                
                with chat_container:
                    with st.chat_message("assistant"):
                        if answer:
                            st.text(answer)
                        if sql:
                            st.code(sql, language='sql')
                    chat_content = []
                    if answer:
                        chat_content.append(answer)
                    if sql:
                        chat_content.append(sql)
                        sql = re.sub(r'\s+', ' ', sql)
                    else:
                        sql = ""
                    logger.info(f"💬 Current Question - {st.session_state.current_question}/n Current Response - {chat_content}")
                    add_to_chat_history(question=None, answer="\n".join(chat_content), table=None)
                
                # Process dataframe if present in the same response
                if 'dataframe' in response:
                    try:
                        df_data = json.loads(response['dataframe'])
                        df = pd.DataFrame(df_data)
                        
                        for col in df.columns:
                            if df[col].dtype == 'object':
                                try:
                                    df[col] = pd.to_datetime(df[col])
                                except:
                                    pass
                        
                        # Store in session state
                        st.session_state.current_dataframe = df
                        
                    except Exception as e:
                        with chat_container:
                            st.error(f"Error processing dataframe: {str(e)}")
                
                # Critical fix: Add rerun to update UI with approval buttons and dataframe
                st.rerun()
                
            # Handle Generic Query
            else:
                if 'current_plot_image' in st.session_state:
                    st.session_state.current_plot_image = None
                answer = response.get('response', 'Sorry, there was an error processing your request. Please rephrase your question or ask another query')
                st.session_state['text_sql_status'].append({"question": user_input, "sql": ""})
                with chat_container:
                    with st.chat_message("assistant"):
                        st.text(answer)
                    add_to_chat_history(question=None, answer=answer, table=None)
            
                # Process dataframe if present and not an SQL query
                if 'dataframe' in response:
                    try:
                        df_data = json.loads(response['dataframe'])
                        df = pd.DataFrame(df_data)
                        
                        for col in df.columns:
                            if df[col].dtype == 'object':
                                try:
                                    df[col] = pd.to_datetime(df[col])
                                except:
                                    pass
                        
                        # Store in session state
                        st.session_state.current_dataframe = df
                        
                        # Rerun to update the data view
                                
                    except Exception as e:
                        with chat_container:
                            st.error(f"Error processing dataframe: {str(e)}")
                        if 'dataframe_error' in response:
                            st.error(f"Server error: {response['dataframe_error']}")
                st.rerun()
    # # Save chat history
    # save_chat_history(st.session_state['text_sql_status'], st.session_state.uid)