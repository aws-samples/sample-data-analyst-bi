FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY UI/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY UI/ .

# Create necessary directories
RUN mkdir -p db_data/chat_out

# Expose port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Run the application
CMD ["streamlit", "run", "Home.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.enableXsrfProtection=false", "--server.enableCORS=false"] 