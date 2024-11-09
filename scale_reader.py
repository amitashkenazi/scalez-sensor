#!/usr/bin/env python3

import os
import sys
import json
import time
import serial
import logging
import decimal
from decimal import Decimal
from datetime import datetime
from pathlib import Path
import traceback
from typing import Optional, Dict, Any, Tuple
from awscrt import io, mqtt
from awsiot import mqtt_connection_builder

# Constants
CONFIG_PATH = '/etc/scale-reader/config.json'
CERTS_PATH = '/etc/scale-reader/certs'
LOG_PATH = '/var/log/scale-reader/scale.log'
TOPIC = "scale-measurements"

# Define certificate filenames
CERT_FILE = 'device.cert.pem'
PRIVATE_KEY = 'device.private.key'
ROOT_CA = 'root-CA.crt'

def setup_logging():
    """Configure logging"""
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_PATH),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logging.info("="*50)
    logging.info("Starting Scale Reader - Single Measurement Mode")
    logging.info(f"Python version: {sys.version}")
    logging.info(f"Log file: {LOG_PATH}")
    logging.info("="*50)

class ScaleConfig:
    """Configuration handler for scale reader"""
    def __init__(self, config_path: str = CONFIG_PATH):
        self.config_path = config_path
        self.data = self._load_config()
    
    def _load_config(self) -> dict:
        try:
            if not os.path.exists(self.config_path):
                raise FileNotFoundError(f"Config file not found at {self.config_path}")
            
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            
            required_fields = [
                'scale_id',
                'serial_port', 
                'baud_rate',
                'iot_endpoint'
            ]
            
            missing = [field for field in required_fields if field not in config]
            if missing:
                raise ValueError(f"Missing required config fields: {missing}")
            
            return config
                
        except Exception as e:
            logging.error(f"Failed to load config: {e}")
            logging.error(traceback.format_exc())
            sys.exit(1)

class ScaleReader:
    """Handles communication with the physical scale"""
    def __init__(self, port: str, baud_rate: int):
        self.port = port
        self.baud_rate = baud_rate
        self.serial = None

    def __enter__(self):
        try:
            logging.info(f"Opening serial port {self.port} at {self.baud_rate} baud")
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                timeout=1,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
            logging.info(f"Serial port settings: {self.serial.get_settings()}")
            return self
        except Exception as e:
            logging.error(f"Failed to connect to scale: {e}")
            logging.error(traceback.format_exc())
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.serial:
            self.serial.close()
            logging.info("Serial port closed")

    def read_weight(self) -> Tuple[bool, Optional[Decimal]]:
        """Read a single weight measurement from scale"""
        try:
            if not self.serial:
                logging.error("Serial port not initialized")
                return False, None

            logging.info("Clearing input buffer")
            self.serial.reset_input_buffer()
            
            # Read with timeout
            start_time = time.time()
            while (time.time() - start_time) < 5:  # 5 second timeout
                if self.serial.in_waiting > 0:
                    raw_data = self.serial.readline()
                    
                    # Log raw data for debugging
                    logging.info("=== Data Received ===")
                    logging.info(f"Raw (hex): {' '.join([f'{b:02x}' for b in raw_data])}")
                    logging.info(f"Raw (chr): {' '.join([chr(b) if 32 <= b <= 126 else '.' for b in raw_data])}")
                    logging.info(f"Length: {len(raw_data)} bytes")
                    
                    try:
                        data = raw_data.decode('ascii').strip()
                        logging.info(f"Decoded data: '{data}'")
                        
                        if not data.startswith('wn'):
                            logging.debug("Skipping partial reading")
                            continue
                            
                        if not data.endswith('kg'):
                            logging.debug("Skipping malformed reading")
                            continue
                        
                        # Extract the numeric part
                        weight_str = data[2:-2]  # Remove 'wn' and 'kg'
                        
                        # Handle negative values
                        if weight_str.startswith('-'):
                            weight_str = weight_str[1:]  # Remove minus sign
                            sign = -1
                        else:
                            sign = 1
                        
                        try:
                            weight = sign * Decimal(weight_str)
                            logging.info(f"Successfully parsed weight: {weight}kg")
                            return True, weight
                        except (ValueError, decimal.InvalidOperation) as e:
                            logging.error(f"Failed to parse weight value '{weight_str}': {e}")
                            continue
                            
                    except UnicodeDecodeError as e:
                        logging.error(f"Failed to decode data: {e}")
                        continue
                
                time.sleep(0.1)
            
            logging.error("Timeout waiting for valid measurement")
            return False, None
                
        except Exception as e:
            logging.error(f"Error reading from scale: {e}")
            logging.error(traceback.format_exc())
            return False, None

class IoTClient:
    """Handles communication with AWS IoT"""
    def __init__(self, scale_id: str, endpoint: str):
        self.scale_id = scale_id
        self.endpoint = endpoint
        self.client_id = f"scale-{scale_id}"
        self.mqtt_connection = self._create_mqtt_client()
        
    def _create_mqtt_client(self):
        """Create MQTT connection to AWS IoT"""
        cert_files = {
            'cert': f"{CERTS_PATH}/{CERT_FILE}",
            'key': f"{CERTS_PATH}/{PRIVATE_KEY}",
            'root': f"{CERTS_PATH}/{ROOT_CA}"
        }
        
        for name, path in cert_files.items():
            if not os.path.exists(path):
                raise FileNotFoundError(f"Missing {name} file: {path}")
            
        logging.info(f"Using certificates from: {CERTS_PATH}")
        logging.info(f"Using client ID: {self.client_id}")
        
        event_loop_group = io.EventLoopGroup(1)
        host_resolver = io.DefaultHostResolver(event_loop_group)
        client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)
        
        return mqtt_connection_builder.mtls_from_path(
            endpoint=self.endpoint,
            cert_filepath=cert_files['cert'],
            pri_key_filepath=cert_files['key'],
            client_bootstrap=client_bootstrap,
            ca_filepath=cert_files['root'],
            client_id=self.client_id,
            clean_session=False,
            keep_alive_secs=30
        )
    
    def connect(self) -> bool:
        """Connect to AWS IoT"""
        try:
            logging.info(f"Connecting to IoT endpoint: {self.endpoint}")
            connect_future = self.mqtt_connection.connect()
            connect_future.result(timeout=10)
            logging.info("Connected to AWS IoT")
            return True
        except Exception as e:
            logging.error(f"Failed to connect to AWS IoT: {e}")
            logging.error(traceback.format_exc())
            return False
    
    def publish_measurement(self, weight: Decimal) -> bool:
        """Publish measurement to AWS IoT"""
        try:
            message = {
                'scale_id': self.scale_id,
                'weight': float(weight),
                'timestamp': datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                'unit': 'kg'
            }
            
            logging.info(f"Publishing message to topic '{TOPIC}': {json.dumps(message, indent=2)}")
            
            # Fixed: Properly handle the future result
            future_connection = self.mqtt_connection.publish(
                topic=TOPIC,
                payload=json.dumps(message),
                qos=mqtt.QoS.AT_LEAST_ONCE
            )
            
            # Wait for the publish to complete
            future, _ = future_connection
            future.result(timeout=5)
            
            logging.info("Measurement published successfully")
            return True
            
        except Exception as e:
            logging.error(f"Error publishing measurement: {e}")
            logging.error(traceback.format_exc())
            return False
    
    def disconnect(self):
        """Disconnect from AWS IoT"""
        try:
            disconnect_future = self.mqtt_connection.disconnect()
            disconnect_future.result(timeout=5)
            logging.info("Disconnected from AWS IoT")
        except Exception as e:
            logging.error(f"Error disconnecting: {e}")
            logging.error(traceback.format_exc())
            
def main():
    """Main function to take single measurement and exit"""
    try:
        setup_logging()
        
        # Load configuration
        config = ScaleConfig()
        
        # Initialize IoT client
        iot_client = IoTClient(config.data['scale_id'], config.data['iot_endpoint'])
        
        # Connect to AWS IoT
        if not iot_client.connect():
            sys.exit(1)

        try:
            # Take a single measurement
            with ScaleReader(config.data['serial_port'], config.data['baud_rate']) as scale:
                logging.info("Taking single measurement...")
                
                success, weight = scale.read_weight()
                
                if success and weight is not None:
                    # Publish measurement
                    if iot_client.publish_measurement(weight):
                        logging.info("Measurement successfully published")
                        sys.exit(0)
                    else:
                        logging.error("Failed to publish measurement")
                        sys.exit(1)
                else:
                    logging.error("Failed to read weight")
                    sys.exit(1)
                    
        finally:
            # Always disconnect properly
            iot_client.disconnect()

    except Exception as e:
        logging.error(f"Fatal error: {e}")
        logging.error(traceback.format_exc())
        sys.exit(1)

if __name__ == '__main__':
    main()