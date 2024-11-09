cd /etc/scale-reader/certs/

# Clean up old files
sudo rm -f test_connection

# Create test script
sudo tee test_connection.py << 'EOL'
#!/usr/bin/env python3
import sys
import time
import json
from awscrt import io, mqtt
from awsiot import mqtt_connection_builder

ENDPOINT = "alyu5ve98pej6.iot.us-east-1.amazonaws.com"
CLIENT_ID = "test_connection"
TEST_TOPIC = "test/connection"

# Create connection
event_loop_group = io.EventLoopGroup(1)
host_resolver = io.DefaultHostResolver(event_loop_group)
client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

mqtt_connection = mqtt_connection_builder.mtls_from_path(
    endpoint=ENDPOINT,
    cert_filepath="device.cert.pem",
    pri_key_filepath="device.private.key",
    client_bootstrap=client_bootstrap,
    ca_filepath="root-CA.crt",
    client_id=CLIENT_ID,
    clean_session=False,
    keep_alive_secs=30
)

print(f"Connecting to {ENDPOINT} with client ID '{CLIENT_ID}'...")
connect_future = mqtt_connection.connect()
connect_future.result()
print("Connected!")

# Test publish
message = {"test": "Hello from device"}
print(f"Publishing message to topic '{TEST_TOPIC}': {message}")
mqtt_connection.publish(
    topic=TEST_TOPIC,
    payload=json.dumps(message),
    qos=mqtt.QoS.AT_LEAST_ONCE
)

# Wait briefly
time.sleep(5)

# Disconnect
print("Disconnecting...")
disconnect_future = mqtt_connection.disconnect()
disconnect_future.result()
print("Disconnected!")
EOL

# Make executable
sudo chmod +x test_connection.py

# Run test
sudo /opt/scale-reader/venv/bin/python3 test_connection.py