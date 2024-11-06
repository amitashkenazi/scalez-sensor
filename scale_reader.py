#!/usr/bin/env python3

import os
import sys
import json
import time
import serial
import logging
import argparse
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import requests

# Constants
CONFIG_PATH = '/etc/scale-reader/config.json'
LOG_PATH = '/var/log/scale-reader/scale.log'
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
API_ENDPOINT = "https://v1kgsjmpn4.execute-api.us-east-1.amazonaws.com/dev/measurements"

class ScaleConfig:
    """Configuration handler for scale reader"""
    def __init__(self, config_path: str = CONFIG_PATH):
        self.config_path = config_path
        self.data = self._load_config()
    
    def _load_config(self) -> dict:
        """Load configuration from JSON file"""
        try:
            if not os.path.exists(self.config_path):
                raise FileNotFoundError(f"Config file not found at {self.config_path}")
            
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            
            # Validate required fields
            required_fields = [
                'scale_id',
                'serial_port', 
                'baud_rate',
                'id_token'  # Now just need the ID token
            ]
            
            missing = [field for field in required_fields if field not in config]
            if missing:
                raise ValueError(f"Missing required config fields: {missing}")
            
            return config
                
        except Exception as e:
            logging.error(f"Failed to load config: {e}")
            sys.exit(1)

class CloudSender:
    """Handles sending data to the cloud service"""
    def __init__(self, config: dict):
        self.config = config
        self.session = requests.Session()

    def send_measurement(self, weight: Decimal) -> bool:
        """Send weight measurement to cloud service"""
        try:
            data = {
                'scale_id': self.config['scale_id'],
                'weight': float(weight),  # Convert Decimal to float
                'timestamp': datetime.utcnow().isoformat(),
                'unit': 'kg'
            }
            
            headers = {
                'Authorization': f'Bearer {self.config["id_token"]}',
                'Content-Type': 'application/json'
            }
            
            # Send request
            response = self.session.post(
                API_ENDPOINT,
                headers=headers,
                json=data,
                timeout=5
            )
            
            # Log response details
            logging.info(f"Response Status: {response.status_code}")
            logging.info(f"Response Body: {response.text}")
            
            if response.status_code == 201:
                logging.info(f"✅ Measurement uploaded successfully: {weight}kg")
                return True
            else:
                logging.error(f"Failed to upload measurement: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logging.error(f"Error sending measurement: {str(e)}")
            return False
                
class ScaleReader:
    """Handles communication with the physical scale via serial connection"""
    def __init__(self, port: str, baud_rate: int):
        self.port = port
        self.baud_rate = baud_rate
        self.serial = None

    def __enter__(self):
        """Context manager entry"""
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                timeout=1,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
            return self
        except Exception as e:
            logging.error(f"Failed to open serial port: {e}")
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if self.serial:
            self.serial.close()

    def read_weight(self) -> Tuple[bool, Optional[Decimal]]:
        """
        Read weight measurement from the scale
        Returns: Tuple of (success, weight)
        """
        try:
            if not self.serial:
                return False, None

            # Clear any existing data in the buffer
            self.serial.reset_input_buffer()
            
            # Read data from scale
            raw_data = self.serial.readline().decode('ascii').strip()
            
            if not raw_data:
                logging.error("No data received from scale")
                return False, None

            # Parse the weight value
            try:
                weight_str = ''.join(c for c in raw_data if c.isdigit() or c == '.')
                weight = Decimal(weight_str).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
                
                if weight < 0 or weight > 1000:  # Adjust range as needed
                    logging.error(f"Weight reading out of valid range: {weight}kg")
                    return False, None
                    
                logging.info(f"Weight reading successful: {weight}kg")
                return True, weight
                
            except (ValueError, decimal.InvalidOperation) as e:
                logging.error(f"Failed to parse weight value '{raw_data}': {e}")
                return False, None

        except serial.SerialException as e:
            logging.error(f"Serial communication error: {e}")
            return False, None
        except Exception as e:
            logging.error(f"Unexpected error reading weight: {e}")
            return False, None

def setup_logging():
    """Configure logging"""
    log_dir = os.path.dirname(LOG_PATH)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=[
            logging.FileHandler(LOG_PATH),
            logging.StreamHandler(sys.stdout)
        ]
    )

def main():
    """Main function"""
    try:
        # Set up argument parser for optional command-line overrides
        parser = argparse.ArgumentParser(description='Scale Reader')
        parser.add_argument('--token', help='Override ID token from config')
        parser.add_argument('--scale-id', help='Override scale ID from config')
        args = parser.parse_args()

        setup_logging()
        logging.info("Starting scale reader...")

        # Load configuration
        config = ScaleConfig()
        
        # Override config with command line arguments if provided
        if args.token:
            config.data['id_token'] = args.token
        if args.scale_id:
            config.data['scale_id'] = args.scale_id

        # Initialize cloud sender
        sender = CloudSender(config.data)

        # Read weight from scale
        with ScaleReader(config.data['serial_port'], config.data['baud_rate']) as scale:
            success, weight = scale.read_weight()
            
            if not success or weight is None:
                logging.error("Failed to read weight")
                sys.exit(1)

            # Send measurement to cloud
            if sender.send_measurement(weight):
                sys.exit(0)
            else:
                sys.exit(1)

    except Exception as e:
        logging.error(f"Fatal error: {str(e)}")
        logging.debug(traceback.format_exc())
        sys.exit(1)

if __name__ == '__main__':
    main()
