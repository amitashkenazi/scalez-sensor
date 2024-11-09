#!/usr/bin/env python3

import os
import sys
import json
import time
import logging
from awscrt import io, mqtt
from awsiot import mqtt_connection_builder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test_connection(
    endpoint="alyu5ve98pej6-ats.iot.us-east-1.amazonaws.com",
    cert_dir="/etc/scale-reader/certs",
    client_id="test-connection"
):
    """Test AWS IoT connection with verbose logging"""
    try:
        logging.info(f"Starting connection test to {endpoint}")
        logging.info(f"Using client ID: {client_id}")
        
        # Verify certificates exist
        cert_files = {
            'cert': f"{cert_dir}/device.cert.pem",
            'key': f"{cert_dir}/device.private.key",
            'root': f"{cert_dir}/root-CA.crt"
        }
        
        for name, path in cert_files.items():
            if not os.path.exists(path):
                raise FileNotFoundError(f"Missing {name} file: {path}")
            logging.info(f"Found {name} file: {path}")
            # Log file permissions
            perms = oct(os.stat(path).st_mode)[-3:]
            logging.info(f"File permissions for {name}: {perms}")
        
        # Create connection
        event_loop_group = io.EventLoopGroup(1)
        host_resolver = io.DefaultHostResolver(event_loop_group)
        client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)
        
        logging.info("Creating MQTT connection...")
        mqtt_connection = mqtt_connection_builder.mtls_from_path(
            endpoint=endpoint,
            cert_filepath=cert_files['cert'],
            pri_key_filepath=cert_files['key'],
            client_bootstrap=client_bootstrap,
            ca_filepath=cert_files['root'],
            client_id=client_id,
            clean_session=False,
            keep_alive_secs=30
        )
        
        logging.info("Attempting to connect...")
        connect_future = mqtt_connection.connect()
        
        # Wait for connection with timeout
        try:
            connect_future.result(timeout=10)
            logging.info("Connected successfully!")
        except Exception as connect_error:
            logging.error(f"Connection failed: {str(connect_error)}")
            return False, f"Connection error: {str(connect_error)}"
        
        # Try publishing a test message
        test_topic = "test/connection"
        test_message = {
            "message": "Test connection successful",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "client_id": client_id
        }
        
        logging.info(f"Publishing test message to {test_topic}")
        publish_future, _ = mqtt_connection.publish(
            topic=test_topic,
            payload=json.dumps(test_message),
            qos=mqtt.QoS.AT_LEAST_ONCE
        )
        
        # Wait for publish confirmation
        try:
            publish_future.result(timeout=5)
            logging.info("Message published successfully!")
        except Exception as publish_error:
            logging.error(f"Publish failed: {str(publish_error)}")
            return False, f"Publish error: {str(publish_error)}"
        
        # Clean disconnect
        logging.info("Disconnecting...")
        disconnect_future = mqtt_connection.disconnect()
        disconnect_future.result()
        logging.info("Disconnected cleanly!")
        
        return True, "Connection test successful!"
        
    except Exception as e:
        error_msg = f"Test failed: {str(e)}"
        logging.error(error_msg)
        return False, error_msg

if __name__ == "__main__":
    print("\nAWS IoT Connection Test")
    print("=" * 50)
    
    # Try with virtual environment python if available
    venv_python = "/opt/scale-reader/venv/bin/python3"
    if os.path.exists(venv_python):
        print(f"Using virtual environment Python: {venv_python}")
    else:
        print("Using system Python")
    
    # Load config to get endpoint
    try:
        with open("/etc/scale-reader/config.json") as f:
            config = json.load(f)
            endpoint = config.get("iot_endpoint")
            scale_id = config.get("scale_id")
            if endpoint and scale_id:
                print(f"Using configuration from config.json:")
                print(f"Endpoint: {endpoint}")
                print(f"Scale ID: {scale_id}")
                success, message = test_connection(
                    endpoint=endpoint,
                    client_id=f"scale-{scale_id}"
                )
            else:
                success, message = test_connection()
    except Exception as e:
        print(f"Error loading config: {e}")
        success, message = test_connection()
    
    print("\nTest Result:", "PASSED" if success else "FAILED")
    print("Message:", message)