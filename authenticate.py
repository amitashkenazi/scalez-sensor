#!/usr/bin/env python3

import os
import sys
import argparse
import logging
from auth_manager import AuthManager

def setup_logging():
    """Configure logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )

def main():
    """Main function to handle authentication"""
    parser = argparse.ArgumentParser(description='Scale Reader Authentication')
    parser.add_argument('--config', default='/etc/scale-reader/config.json',
                       help='Path to config file')
    parser.add_argument('--username', required=True,
                       help='Username for authentication')
    parser.add_argument('--password', required=True,
                       help='Password for authentication')
    
    args = parser.parse_args()
    setup_logging()
    
    # Initialize auth manager
    auth_manager = AuthManager(args.config)
    
    # Authenticate and get token
    success, token, error = auth_manager.authenticate(args.username, args.password)
    
    if not success:
        logging.error(f"Authentication failed: {error}")
        sys.exit(1)
    
    # Update config with new token
    if auth_manager.update_config_with_token(token):
        logging.info("✅ Authentication successful - token updated in config")
        sys.exit(0)
    else:
        logging.error("Failed to update config with new token")
        sys.exit(1)

if __name__ == '__main__':
    main()
