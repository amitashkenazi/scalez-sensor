#!/usr/bin/env python3

import os
import sys
import time
import json
import psutil
import socket
import logging
import subprocess
from typing import Dict, Any
from datetime import datetime
from pathlib import Path
import threading
from queue import Queue
from decimal import Decimal
from awscrt import io, mqtt
from awsiot import mqtt_connection_builder

# Constants
CONFIG_PATH = '/etc/scale-reader/config.json'
CERTS_PATH = '/etc/scale-reader/certs'
LOG_PATH = '/var/log/scale-reader/cloud-control.log'

# MQTT Topics - simplified to match serverless.yml
TOPIC_MEASUREMENTS = "scale-measurements"

def setup_logging():
    """Configure logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        handlers=[
            logging.FileHandler(LOG_PATH, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

class CloudControl:
    def __init__(self, config_path: str = CONFIG_PATH):
        self.config_path = config_path
        self.config = self._load_config()
        self.scale_id = self.config['scale_id']
        self.command_queue = Queue()
        
        # Configure client ID to match policy
        self.client_id = f"scale-{self.scale_id}"
        
        # Initialize MQTT client
        self._verify_certificates()
        self.mqtt = self._create_mqtt_client()

    def _load_config(self) -> dict:
        """Load and validate configuration"""
        try:
            if not os.path.exists(self.config_path):
                raise FileNotFoundError(f"Config file not found at {self.config_path}")
            
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            
            required_fields = ['scale_id', 'serial_port', 'baud_rate', 'iot_endpoint']
            missing = [field for field in required_fields if field not in config]
            
            if missing:
                raise ValueError(f"Missing required config fields: {missing}")
                
            if config['scale_id'] == 'YOUR_SCALE_ID':
                raise ValueError("Please configure scale_id in config.json")
            
            logging.info(f"Loaded config: {json.dumps(config, indent=2)}")
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
            
            # Check file permissions
            stat = os.stat(path)
            if stat.st_mode & 0o777 != 0o600:
                logging.warning(f"Insecure permissions on {name} certificate. Setting to 600")
                os.chmod(path, 0o600)
            
        logging.info("All certificates verified")

    def _create_mqtt_client(self):
        """Create MQTT connection with AWS IoT"""
        try:
            logging.info(f"Creating MQTT client for endpoint: {self.config['iot_endpoint']}")
            
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
            
            logging.info(f"MQTT client created successfully with client ID: {self.client_id}")
            return mqtt_client
            
        except Exception as e:
            logging.error(f"Failed to create MQTT client: {e}")
            raise

    def collect_system_metrics(self) -> Dict[str, Any]:
        """Collect system metrics"""
        metrics = {
            'scale_id': self.scale_id,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'cpu': {
                'percent': psutil.cpu_percent(),
                'temperature': self._get_cpu_temperature()
            },
            'memory': {
                'total': psutil.virtual_memory().total,
                'available': psutil.virtual_memory().available,
                'percent': psutil.virtual_memory().percent
            },
            'disk': {
                'total': psutil.disk_usage('/').total,
                'free': psutil.disk_usage('/').free,
                'percent': psutil.disk_usage('/').percent
            },
            'network': {
                'hostname': socket.gethostname(),
                'ip': self._get_ip_address()
            },
            'uptime': self._get_uptime()
        }
        return metrics

    def _get_cpu_temperature(self) -> float:
        try:
            temp = subprocess.check_output(['vcgencmd', 'measure_temp'])
            return float(temp.decode('utf-8').replace('temp=', '').replace('\'C\n', ''))
        except:
            return 0.0

    def _get_ip_address(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except:
            return "unknown"

    def _get_uptime(self) -> float:
        return psutil.boot_time()

    def run(self):
        """Main run loop"""
        while True:  # Outer loop for reconnection
            try:
                # Connect to AWS IoT
                logging.info("Connecting to AWS IoT Core...")
                connect_future = self.mqtt.connect()
                connect_future.result(timeout=10)
                logging.info("Connected to AWS IoT Core")

                # Main loop
                while True:
                    try:
                        # Collect and publish metrics
                        metrics = self.collect_system_metrics()
                        
                        # Only send essential metrics to measurements topic
                        measurement = {
                            'scale_id': metrics['scale_id'],
                            'weight': 0.0,  # This would be replaced with actual weight
                            'timestamp': metrics['timestamp'],
                            'unit': 'kg'
                        }
                        
                        logging.info(f"Publishing measurement: {json.dumps(measurement, indent=2)}")
                        
                        try:
                            # Publish with timeout
                            publish_future = self.mqtt.publish(
                                topic=TOPIC_MEASUREMENTS,
                                payload=json.dumps(measurement),
                                qos=mqtt.QoS.AT_LEAST_ONCE
                            )
                            publish_future[0].result(timeout=5)
                            logging.info("Published measurement successfully")
                        except Exception as publish_error:
                            logging.error(f"Failed to publish measurement: {str(publish_error)}")
                            # If publish fails, break inner loop to trigger reconnection
                            raise
                        
                        # Wait before next update
                        time.sleep(60)
                        
                    except Exception as loop_error:
                        logging.error(f"Error in main loop: {str(loop_error)}")
                        # Break inner loop to trigger reconnection
                        break
                        
            except Exception as e:
                logging.error(f"Fatal error in connection loop: {str(e)}")
                
            finally:
                try:
                    logging.info("Disconnecting from AWS IoT Core...")
                    disconnect_future = self.mqtt.disconnect()
                    disconnect_future.result(timeout=10)
                    logging.info("Disconnected successfully")
                except Exception as disconnect_error:
                    logging.error(f"Error during disconnect: {str(disconnect_error)}")
            
            # Wait before attempting to reconnect
            logging.info("Waiting 5 seconds before reconnecting...")
            time.sleep(5)
                        
def main():
    """Main entry point"""
    try:
        setup_logging()
        logging.info("Starting Cloud Control Service")
        
        logging.info(f"Python version: {sys.version}")
        logging.info(f"Working directory: {os.getcwd()}")
        
        controller = CloudControl()
        controller.run()
        
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()