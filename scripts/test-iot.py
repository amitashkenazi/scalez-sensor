#!/usr/bin/env python3

import os
import sys
import json
import time
import logging
from awscrt import io, mqtt, auth
from awsiot import mqtt_connection_builder
from concurrent.futures import TimeoutError

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class IoTTestCallbacks:
    def on_connection_success(self, connection, callback_data):
        logging.info("Connection succeeded with callback_data: %s", callback_data)

    def on_connection_failure(self, connection, callback_data):
        logging.error("Connection failed with callback_data: %s", callback_data)

    def on_connection_closed(self, connection, callback_data):
        logging.info("Connection closed with callback_data: %s", callback_data)

    def on_publish_complete(self, topic, packet_id, error_code):
        if error_code:
            logging.error(f"Publish failed for packet_id {packet_id} on topic {topic}. Error: {error_code}")
        else:
            logging.info(f"Publish succeeded for packet_id {packet_id} on topic {topic}")

def test_connection(
    endpoint="alyu5ve98pej6-ats.iot.us-east-1.amazonaws.com",
    
    cert_dir="./certs",
    client_id="test-connection"
):
    mqtt_connection = None
    callbacks = IoTTestCallbacks()
    
    try:
        logging.info(f"Starting connection test to {endpoint}")
        logging.info(f"Using client ID: {client_id}")
        logging.info(f"cert: {cert_dir}/device.cert.pem")
        logging.info(f"key: {cert_dir}/device.private.key")
        logging.info(f"root: {cert_dir}/root-CA.crt")
        
        # Certificate verification
        cert_files = {
            'cert': f"{cert_dir}/device.cert.pem",
            'key': f"{cert_dir}/device.private.key",
            'root': f"{cert_dir}/root-CA.crt"
        }
        
        for name, path in cert_files.items():
            if not os.path.exists(path):
                raise FileNotFoundError(f"Missing {name} file: {path}")
            if not os.access(path, os.R_OK):
                raise PermissionError(f"Cannot read {name} file: {path}")
            logging.info(f"Found {name} file: {path}")
            perms = oct(os.stat(path).st_mode)[-3:]
            logging.info(f"File permissions for {name}: {perms}")
            
            with open(path, 'r') as f:
                content = f.read().strip()
                if not content:
                    raise ValueError(f"{name} file is empty")
                logging.debug(f"{name} file content length: {len(content)} characters")
        
        # Connection setup
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
            keep_alive_secs=30,
            on_connection_success=callbacks.on_connection_success,
            on_connection_failure=callbacks.on_connection_failure,
            on_connection_closed=callbacks.on_connection_closed
        )
        
        # Use allowed topics from the policy
        test_topics = [
            "prod/prod/scale-measurements"
        ]
        
        logging.info("Attempting to connect...")
        connect_future = mqtt_connection.connect()
        
        try:
            connect_future.result(timeout=10)
            logging.info("Connected successfully!")
            
            # Try publishing to allowed topics
            for test_topic in test_topics:
                test_message = {
                    "message": "Test connection successful",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "client_id": client_id,
                    "topic": test_topic,
                    "status": "online"
                }
                
                logging.info(f"Publishing test message to {test_topic}")
                
                try:
                    publish_future, _ = mqtt_connection.publish(
                        topic=test_topic,
                        payload=json.dumps(test_message),
                        qos=mqtt.QoS.AT_LEAST_ONCE
                    )
                    
                    # Wait for publish completion
                    publish_future.result(timeout=5)
                    logging.info(f"Message published successfully to {test_topic}!")
                    return True, f"Connection test successful! Published to {test_topic}"
                    
                except TimeoutError:
                    logging.warning(f"Publish to {test_topic} timed out, trying next topic...")
                    continue
                except Exception as e:
                    logging.warning(f"Failed to publish to {test_topic}: {str(e)}")
                    continue
            
            raise Exception("Failed to publish to any allowed topic")
            
        except TimeoutError:
            raise Exception("Connection timed out after 10 seconds")
        except Exception as e:
            raise Exception(f"Connection failed: {str(e)}")
        
    except Exception as e:
        error_msg = f"Test failed: {str(e)}"
        logging.error(error_msg)
        return False, error_msg

    finally:
        if mqtt_connection:
            try:
                disconnect_future = mqtt_connection.disconnect()
                disconnect_future.result(timeout=3)
                logging.info("Disconnected cleanly!")
            except Exception as e:
                logging.error(f"Error during final disconnect: {str(e)}")

if __name__ == "__main__":
    print("\nAWS IoT Connection Test")
    print("=" * 50)
    
    try:
        with open("./certs/config.json") as f:
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