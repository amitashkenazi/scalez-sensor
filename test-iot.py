import os
import json
import time
import logging
import random
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, Tuple

import boto3
from awscrt import io, mqtt
from awsiot import mqtt_connection_builder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_iot_endpoint() -> Tuple[bool, str]:
    """Get AWS IoT endpoint using boto3"""
    try:
        iot_client = boto3.client('iot')
        response = iot_client.describe_endpoint(
            endpointType='iot:Data-ATS'
        )
        endpoint = response['endpointAddress']
        logging.info(f"Found IoT endpoint: {endpoint}")
        return True, endpoint
    except Exception as e:
        logging.error(f"Failed to get IoT endpoint: {e}")
        return False, ""

class MockScale:
    """Simulates a scale for testing"""
    def __init__(self):
        self.min_weight = 0.0
        self.max_weight = 100.0
    
    def read_weight(self) -> tuple[bool, Optional[Decimal]]:
        """Simulate reading weight from scale"""
        try:
            # Generate random weight for testing
            weight = random.uniform(self.min_weight, self.max_weight)
            return True, Decimal(str(round(weight, 2)))
        except Exception as e:
            logging.error(f"Error reading weight: {e}")
            return False, None

class IoTClient:
    """Handles communication with AWS IoT"""
    def __init__(self, scale_id: str, endpoint: str, cert_dir: str):
        self.scale_id = scale_id
        self.endpoint = endpoint
        self.cert_dir = cert_dir
        self.mqtt_connection = self._create_mqtt_connection()
        
    def _create_mqtt_connection(self):
        """Create MQTT connection to AWS IoT"""
        # Verify certificates exist
        cert_files = {
            'cert': f"{self.cert_dir}/{self.scale_id}.cert.pem",
            'key': f"{self.cert_dir}/{self.scale_id}.private.key",
            'root': f"{self.cert_dir}/root-CA.crt"
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
    
    def connect(self) -> bool:
        """Connect to AWS IoT"""
        try:
            connect_future = self.mqtt_connection.connect()
            connect_future.result()
            logging.info("Connected to AWS IoT")
            return True
        except Exception as e:
            logging.error(f"Failed to connect to AWS IoT: {e}")
            return False
    
    def publish_measurement(self, weight: Decimal, topic: str = "scale-measurements") -> bool:
        """Publish measurement to AWS IoT"""
        try:
            message = {
                'scale_id': self.scale_id,
                'weight': float(weight),
                'timestamp': datetime.utcnow().isoformat(),
                'unit': 'kg'
            }
            
            publish_future, _ = self.mqtt_connection.publish(
                topic=topic,
                payload=json.dumps(message),
                qos=mqtt.QoS.AT_LEAST_ONCE
            )
            publish_future.result()
            
            logging.info(f"✅ Measurement published successfully: {weight}kg")
            return True
            
        except Exception as e:
            logging.error(f"Error publishing measurement: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from AWS IoT"""
        try:
            disconnect_future = self.mqtt_connection.disconnect()
            disconnect_future.result()
            logging.info("Disconnected from AWS IoT")
        except Exception as e:
            logging.error(f"Error disconnecting: {e}")

def setup_test_certificates(scale_id: str, cert_dir: str) -> bool:
    """Set up test certificates using AWS IoT"""
    try:
        # Create IoT client
        iot = boto3.client('iot')
        
        # Check if thing already exists
        thing_name = f"scale-{scale_id}"
        try:
            iot.describe_thing(thingName=thing_name)
            logging.info(f"Thing {thing_name} already exists")
            return True
        except iot.exceptions.ResourceNotFoundException:
            pass
        
        # Create thing
        logging.info(f"Creating new thing: {thing_name}")
        iot.create_thing(
            thingName=thing_name,
            attributePayload={
                'attributes': {
                    'type': 'scale',
                    'scale_id': scale_id
                }
            }
        )
        
        # Create certificate
        cert_response = iot.create_keys_and_certificate(setAsActive=True)
        
        # Save certificate and keys
        os.makedirs(cert_dir, exist_ok=True)
        
        with open(f"{cert_dir}/{scale_id}.cert.pem", 'w') as f:
            f.write(cert_response['certificatePem'])
            
        with open(f"{cert_dir}/{scale_id}.private.key", 'w') as f:
            f.write(cert_response['keyPair']['PrivateKey'])
            
        # Download root CA
        os.system(f"curl https://www.amazontrust.com/repository/AmazonRootCA1.pem -o {cert_dir}/root-CA.crt")
        
        # Attach policy
        policy_name = 'scale-management-system-scale-policy-dev'
        try:
            iot.attach_policy(
                policyName=policy_name,
                target=cert_response['certificateArn']
            )
        except iot.exceptions.ResourceNotFoundException:
            logging.error(f"Policy {policy_name} not found. Please ensure it exists in AWS IoT.")
            return False
        
        # Attach certificate to thing
        iot.attach_thing_principal(
            thingName=thing_name,
            principal=cert_response['certificateArn']
        )
        
        logging.info(f"✅ Test certificates created in: {cert_dir}")
        return True
        
    except Exception as e:
        logging.error(f"Error setting up test certificates: {e}")
        return False

def main():
    """Main test function"""
    # Configuration
    SCALE_ID = "test-scale-1"
    CERT_DIR = "./certs"
    
    try:
        # Get IoT endpoint
        success, endpoint = get_iot_endpoint()
        if not success:
            raise Exception("Failed to get IoT endpoint. Please check your AWS credentials.")
            
        # Set up test certificates
        if not os.path.exists(f"{CERT_DIR}/{SCALE_ID}.cert.pem"):
            if not setup_test_certificates(SCALE_ID, CERT_DIR):
                raise Exception("Failed to set up test certificates")
        
        # Initialize IoT client
        iot_client = IoTClient(SCALE_ID, endpoint, CERT_DIR)
        
        # Connect to AWS IoT
        if not iot_client.connect():
            raise Exception("Failed to connect to AWS IoT")
        
        # Create mock scale
        scale = MockScale()
        
        print("\n" + "="*50)
        print("Test environment ready!")
        print("To monitor messages:")
        print("1. Go to AWS IoT Console")
        print("2. Click on 'Test' in the left navigation")
        print("3. Click on 'MQTT test client'")
        print("4. Subscribe to topic: scale-measurements")
        print("="*50 + "\n")
        
        try:
            # Main test loop
            while True:
                # Read weight from mock scale
                success, weight = scale.read_weight()
                
                if not success or weight is None:
                    logging.error("Failed to read weight")
                    continue
                
                # Publish measurement
                iot_client.publish_measurement(weight)
                
                # Wait before next reading
                time.sleep(10)
                
        except KeyboardInterrupt:
            logging.info("Test stopped by user")
        finally:
            # Clean up
            iot_client.disconnect()
            
    except Exception as e:
        logging.error(f"Test failed: {str(e)}")

if __name__ == '__main__':
    main()