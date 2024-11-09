import requests
import json
import logging
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta

class AuthManager:
    """Handles authentication and token management"""
    
    # Update these endpoints to match your actual authentication endpoints
    AUTH_ENDPOINT = "https://cognito-idp.us-east-1.amazonaws.com/"
    CLIENT_ID = "1jt9sr5fqjd4af378rjt9ferfk"  # Add your Cognito client ID
    
    def __init__(self, config_path: str):
        self.config_path = config_path
        
    def authenticate(self, username: str, password: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Authenticate user using Amazon Cognito
        Returns: Tuple of (success, token, error_message)
        """
        try:
            headers = {
                'X-Amz-Target': 'AWSCognitoIdentityProviderService.InitiateAuth',
                'Content-Type': 'application/x-amz-json-1.1'
            }
            
            payload = {
                'AuthFlow': 'USER_PASSWORD_AUTH',
                'ClientId': self.CLIENT_ID,
                'AuthParameters': {
                    'USERNAME': username,
                    'PASSWORD': password
                }
            }
            
            response = requests.post(
                self.AUTH_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                auth_result = response.json().get('AuthenticationResult', {})
                id_token = auth_result.get('IdToken')
                if id_token:
                    return True, id_token, None
                return False, None, "No token in response"
            
            error_msg = f"Authentication failed: {response.status_code} - {response.text}"
            logging.error(f"Full response: {response.text}")
            return False, None, error_msg
            
        except Exception as e:
            return False, None, f"Authentication error: {str(e)}"
    
    def update_config_with_token(self, token: str) -> bool:
        """
        Update the config file with the new token
        Returns: bool indicating success
        """
        try:
            # Read existing config
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            
            # Update token
            config['id_token'] = token
            
            # Write updated config
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=4)
            
            logging.info("Config file updated successfully")
            return True
            
        except Exception as e:
            logging.error(f"Failed to update config with token: {e}")
            return False
