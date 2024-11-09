#!/usr/bin/env python3

"""
Authentication setup script for scale reader.
This script helps set up the initial authentication tokens.
"""

import os
import sys
import json
import time
import logging
import argparse
from pathlib import Path

CONFIG_PATH = '/etc/scale-reader/config.json'
TOKEN_PATH = '/etc/scale-reader/token.json'

def setup_tokens(id_token: str, access_token: str, refresh_token: str):
    """Save the authentication tokens"""
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        
        # Save tokens
        tokens = {
            'id_token': id_token,
            'access_token': access_token,
            'refresh_token': refresh_token,
            'saved_at': time.time()
        }
        
        with open(TOKEN_PATH, 'w') as f:
            json.dump(tokens, f)
        
        # Secure the token file
        os.chmod(TOKEN_PATH, 0o600)
        
        print("✅ Tokens saved successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error saving tokens: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Setup authentication for scale reader')
    parser.add_argument('--id-token', required=True, help='Cognito ID token')
    parser.add_argument('--access-token', required=True, help='Cognito access token')
    parser.add_argument('--refresh-token', required=True, help='Cognito refresh token')
    
    args = parser.parse_args()
    
    if setup_tokens(args.id_token, args.access_token, args.refresh_token):
        print("\nAuthentication setup complete!")
        print(f"Token file saved to: {TOKEN_PATH}")
        print("\nThe scale reader will now use these tokens for authentication")
    else:
        print("\n❌ Authentication setup failed")
        sys.exit(1)

if __name__ == '__main__':
    main()
