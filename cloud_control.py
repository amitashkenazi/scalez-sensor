#!/usr/bin/env python3

import os
import sys
import time
import json
import logging
import random
from datetime import datetime
from awscrt import io, mqtt
from awsiot import mqtt_connection_builder

# Constants
CONFIG_PATH = './certs/config.json'
CERTS_PATH = './certs'
LOG_PATH = '/tmp/cloud-control.log'
COMMANDS_TOPIC = "scale-commands"
STATUS_TOPIC = "scale-status"

def setup_logging():
    """Configure logging"""
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,  # Enable detailed logs
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_PATH),
            logging.StreamHandler(sys.stdout)
        ]
    )

class CloudControl:
    def __init__(self):
        self.config = self._load_config()
        self.device_id = self.config['device_id']
        self.client_id = f"device-{self.device_id}"
        self._verify_certificates()
        self.mqtt = None  # Initialize MQTT client as None
        
    def _load_config(self):
        """Load and validate configuration"""
        try:
            if not os.path.exists(CONFIG_PATH):
                raise FileNotFoundError(f"Config file not found at {CONFIG_PATH}")
            logging.info(f"Loading config from {CONFIG_PATH}")
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)
            logging.info(f"Config loaded: {config}")
            required_fields = ['device_id', 'iot_endpoint']
            missing = [field for field in required_fields if field not in config]
            
            if missing:
                raise ValueError(f"Missing required config fields: {missing}")
            
            return config
            
        except Exception as e:
            logging.error(f"Failed to load config: {e}")
            raise

    def _verify_certificates(self):
        """Verify all required certificates exist"""
        cert_files = {
            'cert': f"{CERTS_PATH}/device.cert.pem",
            'key': f"{CERTS_PATH}/device.private.key",
            'root': f"{CERTS_PATH}/root-CA.crt"
        }
        
        for name, path in cert_files.items():
            if not os.path.exists(path):
                raise FileNotFoundError(f"Missing {name} certificate: {path}")
        
        logging.info("All certificates verified")

    def _create_mqtt_client(self):
        """Create MQTT connection with AWS IoT"""
        try:
            event_loop_group = io.EventLoopGroup(1)
            host_resolver = io.DefaultHostResolver(event_loop_group)
            client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)
            
            mqtt_client = mqtt_connection_builder.mtls_from_path(
                endpoint=self.config['iot_endpoint'],
                cert_filepath=f"{CERTS_PATH}/device.cert.pem",
                pri_key_filepath=f"{CERTS_PATH}/device.private.key",
                client_bootstrap=client_bootstrap,
                ca_filepath=f"{CERTS_PATH}/root-CA.crt",
                client_id=self.client_id,
                clean_session=True,  # Ensure a clean session on reconnect
                keep_alive_secs=30
            )
            
            return mqtt_client
            
        except Exception as e:
            logging.error(f"Failed to create MQTT client: {e}")
            raise

    def _disconnect_mqtt(self):
        """Disconnect MQTT client"""
        if self.mqtt:
            try:
                disconnect_future = self.mqtt.disconnect()
                disconnect_future.result(timeout=10)
                logging.info("Disconnected from AWS IoT Core")
            except Exception as e:
                logging.warning(f"Error during MQTT disconnect: {e}")

    
    def _clear_previous_requests(self):
        """Clear any previous requests to avoid session conflicts"""
        try:
            if self.mqtt:
                disconnect_future = self.mqtt.disconnect()
                disconnect_future.result(timeout=10)
        except Exception as e:
            logging.warning(f"Could not properly clear previous session: {e}")
                
                
    def _exponential_backoff(self, base=2, factor=1, max_time=60):
        """Exponential backoff for retries"""
        retry_time = min(base * factor + random.uniform(0, 1), max_time)
        logging.info(f"Retrying in {retry_time:.2f} seconds...")
        time.sleep(retry_time)
        return factor * 2  # Increase backoff factor

    def handle_command(self, topic, payload, **kwargs):
        """Handle incoming commands"""
        try:
            payload_text = payload.decode('utf-8')
            command = json.loads(payload_text)
            logging.info(f"Received command: {command}")
        except Exception as e:
            logging.error(f"Error handling command: {e}")
    
    def _publish_status(self, status_data):
        """Publish status update to AWS IoT"""
        try:
            status_data.update({
                'device_id': self.device_id,
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            })
            
            self.mqtt.publish(
                topic=STATUS_TOPIC,
                payload=json.dumps(status_data),
                qos=mqtt.QoS.AT_LEAST_ONCE
            )
        except Exception as e:
            logging.error(f"Error publishing status: {e}")

    def run(self):
        """Main run loop with reconnection logic"""
        backoff_factor = 1
        while True:
            try:
                # Disconnect before reconnecting
                if self.mqtt:
                    self._disconnect_mqtt()

                # Create a fresh MQTT client
                self.mqtt = self._create_mqtt_client()

                # Connect to AWS IoT
                logging.info("Connecting to AWS IoT Core...")
                connect_future = self.mqtt.connect()
                connect_future.result(timeout=10)
                logging.info("Connected to AWS IoT Core")

                # Subscribe to commands
                subscribe_future, _ = self.mqtt.subscribe(
                    topic=f"{COMMANDS_TOPIC}/{self.device_id}",
                    qos=mqtt.QoS.AT_LEAST_ONCE,
                    callback=self.handle_command
                )
                subscribe_future.result(timeout=10)
                logging.info(f"Subscribed to {COMMANDS_TOPIC}/{self.device_id}")

                # Reset backoff on successful connection
                backoff_factor = 1

                # Main loop
                while True:
                    time.sleep(60)  # Wake up every minute to check connection

            except Exception as e:
                logging.error(f"Error in main loop: {e}")

                # Use exponential backoff before reconnecting
                backoff_factor = self._exponential_backoff(factor=backoff_factor)
                
def main():
    """Main entry point"""
    try:
        setup_logging()
        logging.info("Starting Cloud Control Service")
        controller = CloudControl()
        controller.run()
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()