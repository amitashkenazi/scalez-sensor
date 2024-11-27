#!/usr/bin/env python3

import os
import sys
import json
import logging
import decimal
from decimal import Decimal
from datetime import datetime
import serial
from awscrt import io, mqtt
from awsiot import mqtt_connection_builder
import time
import json

# Constants
CONFIG_PATH = '/etc/scale-reader/config.json'
CERTS_PATH = '/home/amitash/certs'
LOG_PATH = '/tmp/scale.log'
STAGE = 'prod'  # This should match your deployment stage
TOPIC = f"{STAGE}/{STAGE}/scale-measurements"  # Changed to match IoT rule


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
                'iot_endpoint',
                'stage'  # Add stage to required fields
            ]
            
            missing = [field for field in required_fields if field not in config]
            if missing:
                raise ValueError(f"Missing required config fields: {missing}")
            
            return config
                
        except Exception as e:
            logging.error(f"Failed to load config: {e}")
            raise

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
                timeout=2,  # Increased timeout
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
            return self
        except Exception as e:
            logging.error(f"Failed to connect to scale: {e}")
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.serial:
            self.serial.close()
            logging.info("Serial port closed")

    def read_weight(self):
        """Read a single weight measurement from scale"""
        try:
            if not self.serial:
                raise Exception("Serial port not initialized")

            # Clear any stale data
            self.serial.reset_input_buffer()
            time.sleep(0.1)  # Short delay to allow new data
            
            # Wait for data to be available
            max_attempts = 5
            attempt = 0
            
            while attempt < max_attempts:
                if self.serial.in_waiting > 0:
                    raw_data = self.serial.readline()
                    
                    logging.info("=== Data Received ===")
                    logging.info(f"Raw (hex): {' '.join([f'{b:02x}' for b in raw_data])}")
                    logging.info(f"Raw (chr): {' '.join([chr(b) if 32 <= b <= 126 else '.' for b in raw_data])}")
                    logging.info(f"Length: {len(raw_data)} bytes")
                    
                    try:
                        data = raw_data.decode('ascii').strip()
                        logging.info(f"Decoded data: '{data}'")
                        
                        if data.startswith('wn') and data.endswith('kg'):
                            # Extract the numeric part
                            weight_str = data[2:-2]  # Remove 'wn' and 'kg'
                            
                            # Handle negative values
                            sign = -1 if weight_str.startswith('-') else 1
                            weight_str = weight_str[1:] if sign == -1 else weight_str
                            
                            weight = sign * Decimal(weight_str)
                            logging.info(f"Successfully parsed weight: {weight}kg")
                            return weight
                    except Exception as decode_error:
                        logging.error(f"Error decoding data: {decode_error}")
                        
                attempt += 1
                time.sleep(0.5)  # Wait for more data
                
            raise Exception("No valid weight data received from scale")
                
        except Exception as e:
            logging.error(f"Error reading from scale: {e}")
            raise

class IoTClient:
    """Handles communication with AWS IoT"""
    def __init__(self, scale_id: str, endpoint: str, stage: str = STAGE):
        logging.info(f"Initializing IoT client for scale {scale_id} in stage {stage} with endpoint {endpoint}")
        self.scale_id = scale_id
        self.endpoint = endpoint
        self.stage = stage
        self.mqtt_connection = self._create_mqtt_connection()
        
    def _create_mqtt_connection(self):
        """Create MQTT connection to AWS IoT"""
        logging.info(f"Creating MQTT connection CERTS_PATH: {CERTS_PATH}")
        cert_files = {
            'cert': f"{CERTS_PATH}/device.cert.pem",
            'key': f"{CERTS_PATH}/device.private.key",
            'root': f"{CERTS_PATH}/root-CA.crt"
        }
        
        for name, path in cert_files.items():
            if not os.path.exists(path):
                raise FileNotFoundError(f"Missing {name} file: {path}")
        
        event_loop_group = io.EventLoopGroup(1)
        host_resolver = io.DefaultHostResolver(event_loop_group)
        client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)
        
        return mqtt_connection_builder.mtls_from_path(
            endpoint=self.endpoint,
            cert_filepath=cert_files['cert'],
            pri_key_filepath=cert_files['key'],
            client_bootstrap=client_bootstrap,
            ca_filepath=cert_files['root'],
            client_id=f"scale-{self.scale_id}",
            clean_session=False,
            keep_alive_secs=30
        )
    
    def connect(self):
        """Connect to AWS IoT"""
        try:
            connect_future = self.mqtt_connection.connect()
            connect_future.result(timeout=10)
            logging.info("Connected to AWS IoT")
        except Exception as e:
            logging.error(f"Failed to connect to AWS IoT: {e}")
            raise
    
    def publish_measurement(self, weight: Decimal):
        """Publish measurement to AWS IoT"""
        try:
            topic = f"{self.stage}/{self.stage}/scale-measurements"
            message = {
                'measurement_id': f"{self.scale_id}-{int(time.time())}",
                'scale_id': self.scale_id,
                'weight': float(weight),
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'unit': 'kg'
            }
            
            logging.info(f"Publishing message to topic '{topic}': {json.dumps(message, indent=2)}")
            
            future, _ = self.mqtt_connection.publish(
                topic=topic,
                payload=json.dumps(message),
                qos=mqtt.QoS.AT_LEAST_ONCE
            )
            
            try:
                future.result(timeout=10)
                logging.info("Measurement published successfully")
            except Exception as publish_error:
                raise Exception(f"Failed to publish: {str(publish_error)}")
                
        except Exception as e:
            logging.error(f"Error publishing measurement: {e}")
            raise

    def disconnect(self):
        """Disconnect from AWS IoT"""
        try:
            disconnect_future = self.mqtt_connection.disconnect()
            disconnect_future.result(timeout=10)
            logging.info("Disconnected from AWS IoT")
        except Exception as e:
            logging.error(f"Error disconnecting: {e}")

def main():
    """Main function to take single measurement and exit"""
    try:
        setup_logging()
        logging.info("Starting single measurement process")
        
        # Load configuration
        config = ScaleConfig()
        logging.info("Configuration loaded successfully")  
        # Initialize IoT client
        iot_client = IoTClient(config.data['scale_id'], config.data['iot_endpoint'])
        logging.info("IoT client initialized")
        # Connect to AWS IoT
        iot_client.connect()
        logging.info("Connected to AWS IoT") 
        
        try:
            # Take a single measurement
            with ScaleReader(config.data['serial_port'], config.data['baud_rate']) as scale:
                weight = scale.read_weight()
                iot_client.publish_measurement(weight)
                logging.info("Measurement taken and published successfully")
                sys.exit(0)
                
        finally:
            iot_client.disconnect()

    except Exception as e:
        logging.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()