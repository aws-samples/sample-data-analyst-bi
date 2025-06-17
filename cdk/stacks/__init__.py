# Empty file to make this directory a Python package 

import logging
import os
import platform

def setup_logger(name: str) -> logging.Logger:
    """Setup logger with debug level based on environment variable."""
    logger = logging.getLogger(name)
    
    # Only configure if not already configured
    if not logger.handlers:
        # Set level based on environment variable
        log_level = os.getenv('CDK_LOG_LEVEL', 'INFO').upper()
        logger.setLevel(getattr(logging, log_level, logging.INFO))
        
        # Create console handler
        handler = logging.StreamHandler()
        handler.setLevel(logger.level)
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        
        # Add handler to logger
        logger.addHandler(handler)
    
    return logger 

# Export stack classes
from .backend_stack import BackendStack
from .frontend_stack import FrontendStack  
from .vpc_endpoints_stack import VpcEndpointsStack

__all__ = ["BackendStack", "FrontendStack", "VpcEndpointsStack", "setup_logger"] 