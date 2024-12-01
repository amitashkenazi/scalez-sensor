#!/usr/bin/env python3

import os
import json
import time
import logging
from awscrt import io, mqtt
from awsiot import mqtt_connection_builder
from concurrent.futures import TimeoutError

logging.basicConfig(level=logging.DEBUG)

def test_mqtt_connection(endpoint, cert_path, key_path, root_ca_path, client_id, verbose=True):
    """Test MQTT connection with different parameters to diagnose issues"""
    results = []
    
    def on_connection_success(connection, callback_data):
        results.append(("Connection succeeded", callback_data))
        
    def on_connection_failure(connection, callback_data):
        results.append(("Connection failed", callback_data))
        
    def on_connection_closed(connection, callback_data):
        results.append(("Connection closed", callback_data))

    # Test different client IDs
    client_ids_to_test = [
        client_id,
        f"test_{client_id}",
        "diagnostic_client",
        f"diagnostic_{int(time.time())}"
    ]
    
    for test_client_id in client_ids_to_test:
        if verbose:
            print(f"\nTesting with client ID: {test_client_id}")
            
        try:
            event_loop_group = io.EventLoopGroup(1)
            host_resolver = io.DefaultHostResolver(event_loop_group)
            client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)
            
            mqtt_connection = mqtt_connection_builder.mtls_from_path(
                endpoint=endpoint,
                cert_filepath=cert_path,
                pri_key_filepath=key_path,
                client_bootstrap=client_bootstrap,
                ca_filepath=root_ca_path,
                client_id=test_client_id,
                clean_session=True,
                keep_alive_secs=30,
                on_connection_success=on_connection_success,
                on_connection_failure=on_connection_failure,
                on_connection_closed=on_connection_closed
            )
            
            if verbose:
                print("Attempting to connect...")
                
            connect_future = mqtt_connection.connect()
            
            try:
                connect_future.result(timeout=10)
                if verbose:
                    print("✅ Connection successful!")
                    
                # Try a test publish
                test_topic = "diagnostic/test"
                test_message = {
                    "test": "message",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "client_id": test_client_id
                }
                
                if verbose:
                    print(f"Attempting to publish to {test_topic}")
                    
                publish_future, _ = mqtt_connection.publish(
                    topic=test_topic,
                    payload=json.dumps(test_message),
                    qos=mqtt.QoS.AT_LEAST_ONCE
                )
                
                publish_future.result(timeout=10)
                if verbose:
                    print("✅ Publish successful!")
                    
            except TimeoutError:
                if verbose:
                    print("❌ Connection timed out")
                results.append((test_client_id, "Connection timeout"))
            except Exception as e:
                if verbose:
                    print(f"❌ Connection failed: {str(e)}")
                results.append((test_client_id, f"Error: {str(e)}"))
            finally:
                if mqtt_connection:
                    disconnect_future = mqtt_connection.disconnect()
                    disconnect_future.result(timeout=10)
                    if verbose:
                        print("Disconnected")
                        
        except Exception as e:
            if verbose:
                print(f"❌ Setup failed: {str(e)}")
            results.append((test_client_id, f"Setup Error: {str(e)}"))
            
    return results

if __name__ == "__main__":
    print("\nAWS IoT MQTT Connection Diagnostics")
    print("=" * 50)
    
    cert_dir = "./certs"
    
    # Try to load config
    try:
        with open(f"{cert_dir}/config.json") as f:
            config = json.load(f)
            endpoint = config.get("iot_endpoint", "alyu5ve98pej6-ats.iot.us-east-1.amazonaws.com")
            scale_id = config.get("scale_id", "test")
    except Exception:
        endpoint = "alyu5ve98pej6-ats.iot.us-east-1.amazonaws.com"
        scale_id = "test"
    
    cert_files = {
        'cert': f"{cert_dir}/device.cert.pem",
        'key': f"{cert_dir}/device.private.key",
        'root': f"{cert_dir}/root-CA.crt"
    }
    
    results = test_mqtt_connection(
        endpoint=endpoint,
        cert_path=cert_files['cert'],
        key_path=cert_files['key'],
        root_ca_path=cert_files['root'],
        client_id=f"scale-{scale_id}"
    )
    
    print("\nTest Results:")
    print("=" * 50)
    for client_id, result in results:
        print(f"\nClient ID: {client_id}")
        print(f"Result: {result}")