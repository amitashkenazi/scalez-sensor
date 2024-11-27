#!/usr/bin/env python3

import os
import sys
import time
import json
import psutil
import socket
import logging
import subprocess
from datetime import datetime
from awscrt import io, mqtt
from awsiot import mqtt_connection_builder

# Constants
CONFIG_PATH = '/etc/scale-reader/config.json'
CERTS_PATH = '/etc/scale-reader/certs'
LOG_PATH = '/var/log/scale-reader/cloud-control.log'
COMMANDS_TOPIC = "scale-commands"  # Topic for receiving commands
STATUS_TOPIC = "scale-status"      # Topic for sending status updates

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

class CloudControl:
    def __init__(self):
        self.config = self._load_config()
        self.scale_id = self.config['scale_id']
        self.client_id = f"scale-{self.scale_id}"
        self._verify_certificates()
        self.mqtt = self._create_mqtt_client()
        
    def _load_config(self):
        """Load and validate configuration"""
        try:
            if not os.path.exists(CONFIG_PATH):
                raise FileNotFoundError(f"Config file not found at {CONFIG_PATH}")
            
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)
            
            required_fields = ['scale_id', 'iot_endpoint']
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
                clean_session=False,
                keep_alive_secs=30
            )
            
            return mqtt_client
            
        except Exception as e:
            logging.error(f"Failed to create MQTT client: {e}")
            raise

    def handle_command(self, topic, payload, **kwargs):
        """Handle incoming commands"""
        try:
            payload_text = payload.decode('utf-8')
            command = json.loads(payload_text)
            logging.info(f"Received command: {command}")
            
            if 'action' in command:
                if command['action'] == 'set_sampling_rate':
                    self._handle_sampling_rate(command)
                else:
                    logging.warning(f"Unknown command action: {command['action']}")
                    
        except Exception as e:
            logging.error(f"Error handling command: {e}")
    
    def _handle_sampling_rate(self, command):
        """Handle sampling rate change command"""
        try:
            if 'rate' not in command:
                raise ValueError("Missing 'rate' parameter")
                
            rate = command['rate'].upper()
            if rate not in ['FAST', 'SLOW']:
                raise ValueError("Rate must be 'FAST' or 'SLOW'")
                
            # Convert rate to minutes
            minutes = 1 if rate == 'FAST' else 30
            
            # Update crontab
            result = subprocess.run(
                ['/usr/local/bin/scale-interval', str(minutes)],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                logging.info(f"Successfully set sampling rate to {rate} ({minutes} minutes)")
                self._publish_status({
                    'status': 'success',
                    'message': f"Sampling rate set to {rate}",
                    'sampling_rate': rate,
                    'interval_minutes': minutes
                })
            else:
                raise Exception(f"Failed to update sampling rate: {result.stderr}")
                
        except Exception as e:
            error_msg = f"Error setting sampling rate: {str(e)}"
            logging.error(error_msg)
            self._publish_status({
                'status': 'error',
                'message': error_msg
            })
    
    def _publish_status(self, status_data):
        """Publish status update to AWS IoT"""
        try:
            status_data.update({
                'scale_id': self.scale_id,
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
        """Main run loop"""
        while True:  # Outer loop for reconnection
            try:
                # Connect to AWS IoT
                logging.info("Connecting to AWS IoT Core...")
                connect_future = self.mqtt.connect()
                connect_future.result(timeout=10)
                logging.info("Connected to AWS IoT Core")
                
                # Subscribe to commands
                subscribe_future, _ = self.mqtt.subscribe(
                    topic=f"{COMMANDS_TOPIC}/{self.scale_id}",
                    qos=mqtt.QoS.AT_LEAST_ONCE,
                    callback=self.handle_command
                )
                subscribe_future.result(timeout=10)
                logging.info(f"Subscribed to {COMMANDS_TOPIC}/{self.scale_id}")
                
                # Main loop
                while True:
                    time.sleep(60)  # Wake up every minute to check connection
                    
            except Exception as e:
                logging.error(f"Error in main loop: {e}")
                time.sleep(5)  # Wait before reconnecting
                continue

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