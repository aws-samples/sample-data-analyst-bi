import os
import socket
import logging
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def debug_network_connectivity():
    """Debug network connectivity issues"""
    
    # Get configuration
    host = "data-analyst-workgroup.203918850931.us-east-1.redshift-serverless.amazonaws.com"
    port = 5439
    
    logger.info("=== Network Connectivity Debug ===")
    logger.info(f"Target: {host}:{port}")
    
    # Test 1: DNS Resolution
    logger.info("1. Testing DNS resolution...")
    try:
        ip_address = socket.gethostbyname(host)
        logger.info(f"✓ DNS resolved: {host} -> {ip_address}")
    except Exception as e:
        logger.error(f"✗ DNS resolution failed: {e}")
        return False
    
    # Test 2: Basic TCP connection
    logger.info("2. Testing TCP connection...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        
        start_time = time.time()
        result = sock.connect_ex((ip_address, port))
        end_time = time.time()
        
        if result == 0:
            logger.info(f"✓ TCP connection successful in {end_time - start_time:.2f} seconds")
            sock.close()
        else:
            logger.error(f"✗ TCP connection failed with error code: {result}")
            logger.error("Common error codes:")
            logger.error("  11 = Resource temporarily unavailable")
            logger.error("  111 = Connection refused")
            logger.error("  110 = Connection timed out")
            sock.close()
            return False
            
    except Exception as e:
        logger.error(f"✗ TCP connection test failed: {e}")
        return False
    
    # Test 3: Check local network info
    logger.info("3. Checking local network configuration...")
    try:
        # Get local IP
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        logger.info(f"Local hostname: {hostname}")
        logger.info(f"Local IP: {local_ip}")
        
        # Check if we're in a VPC (private IP ranges)
        if local_ip.startswith('10.') or local_ip.startswith('172.') or local_ip.startswith('192.168.'):
            logger.info("✓ Lambda appears to be in a VPC (private IP)")
        else:
            logger.warning("⚠ Lambda might not be in expected VPC")
            
    except Exception as e:
        logger.error(f"✗ Local network check failed: {e}")
    
    # Test 4: Check internet connectivity (to verify egress)
    logger.info("4. Testing internet connectivity...")
    try:
        # Test connection to a public service
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex(("8.8.8.8", 53))  # Google DNS
        sock.close()
        
        if result == 0:
            logger.info("✓ Internet connectivity working (egress available)")
        else:
            logger.warning("⚠ No internet connectivity (might be in isolated subnet)")
            
    except Exception as e:
        logger.warning(f"⚠ Internet connectivity test failed: {e}")
    
    # Test 5: Environment variables
    logger.info("5. Checking environment variables...")
    important_vars = ['AWS_REGION', 'AWS_LAMBDA_FUNCTION_NAME', 'AWS_LAMBDA_FUNCTION_VERSION']
    for var in important_vars:
        value = os.environ.get(var, 'NOT SET')
        logger.info(f"{var}: {value}")
    
    logger.info("=== Debug Complete ===")
    return True

if __name__ == "__main__":
    debug_network_connectivity() 