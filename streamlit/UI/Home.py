import streamlit as st

# Page configuration - should be the first Streamlit command
st.set_page_config(
    page_title="Data Analyst Platform",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state for persona if not exists
if 'persona' not in st.session_state:
    st.session_state['persona'] = "Admin"

# Automatically redirect to DataAnalyst page
st.switch_page("pages/DataAnalyst.py")

# Center the content with columns
col1, col2, col3 = st.columns([1, 2, 1])

with col2:
    # Title and description
    st.title("🤖 Data Analyst Platform")
    st.markdown("---")
    
    # Profile Selection
    st.subheader("👤 Select Your Profile")
    
    # Profile options
    profile_options = [
        "Data Analyst",
        "Business Analyst", 
        "Data Scientist",
        "Product Manager",
        "Marketing Analyst",
        "Financial Analyst",
        "Operations Analyst"
    ]
    
    # Profile selection dropdown
    selected_persona = st.selectbox(
        "Choose your role:",
        options=profile_options,
        index=profile_options.index(st.session_state.get('persona', 'Data Analyst')),
        help="Select your professional role to get personalized responses and insights."
    )
    
    # Update session state when selection changes
    if selected_persona != st.session_state.get('persona'):
        st.session_state['persona'] = selected_persona
        st.success(f"✅ Profile updated to: {selected_persona}")
    
    st.markdown("---")
    
    # Navigation instruction
    st.info("👈 Navigate to **DataAnalyst** in the sidebar to start analyzing your data!", icon="💡")
    
    # Current profile display
    st.markdown(f"**Current Profile:** {st.session_state['persona']}")

# streamlit run home.py --server.address=0.0.0.0 --server.baseUrlPath="/proxy/absolute/8501" --server.enableXsrfProtection false
# https://{notebook instance name}.notebook.{region name}.sagemaker.aws/proxy/absolute/8501/

#https://testvpc2.notebook.us-east-1.sagemaker.aws/proxy/absolute/8501/