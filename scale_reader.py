#!/usr/bin/env python3

import os
import sys
import json
import logging
import decimal
import argparse
from decimal import Decimal
from datetime import datetime
import serial
from awscrt import io, mqtt
from awsiot import mqtt_connection_builder
import time
import json
from bluepy.btle import Scanner, DefaultDelegate, Peripheral, BTLEDisconnectError
import subprocess

# Constants
CONFIG_PATH = '/home/amitash/certs/config.json'
CERTS_PATH = '/home/amitash/certs'
LOG_PATH = '/tmp/scale.log'
STAGE = 'prod'
TOPIC = f"{STAGE}/{STAGE}/scale-measurements"

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
    def __init__(self, device, config_path: str = CONFIG_PATH):
        self.config_path = config_path
        self.data = self._load_config(device)
    
    def _load_config(self, device) -> dict:
        try:
            logging.info(f"Loading configuration from {self.config_path}")
            if not os.path.exists(self.config_path):
                raise FileNotFoundError(f"Config file not found at {self.config_path}")
            
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            
            required_fields = [
                'device_id',
                'iot_endpoint',
                'stage',
            ]
            if device == 'rs232':
                required_fields += ['serial_port', 'baud_rate']
            elif device == 'bluetooth':
                required_fields += ['bluetooth_mac']
            
            missing = [field for field in required_fields if field not in config]
            if missing:
                raise ValueError(f"Missing required config fields: {missing}")
            
            return config
                
        except Exception as e:
            logging.error(f"Failed to load config: {e}")
            raise

class NotificationDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)
        self.last_weight = None
        self.weight_received = False

    def handleNotification(self, cHandle, data):
        try:
            logging.info(f"Received data: {data.hex()}")
            logging.info("Data bytes: " + " ".join([f"{b:02x}" for b in data]))
            
            text_data = data.decode('ascii').strip()
            logging.info(f"Decoded text: {text_data}")
            
            if text_data.startswith('sg') and text_data.endswith('kg'):
                weight_str = text_data[2:-2]
                self.last_weight = Decimal(weight_str)
                logging.info(f"Parsed weight: {self.last_weight} kg")
                self.weight_received = True
        except Exception as e:
            logging.error(f"Error parsing notification: {e}")

class BluetoothScale:
    """Bluetooth Scale Handler"""
    def __init__(self, device_id, mac_address):
        self.device_id = device_id
        self.mac_address = mac_address
        self.NOTIFY_CHARACTERISTIC_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
        self.connection_retries = 3
        self.retry_delay = 2

    def setup_bluetooth(self):
        try:
            subprocess.run(['sudo', 'hciconfig', 'hci0', 'down'], check=True)
            time.sleep(1)
            subprocess.run(['sudo', 'hciconfig', 'hci0', 'up'], check=True)
            time.sleep(1)
            subprocess.run(['sudo', 'hciconfig', 'hci0', 'leadv', '0'], check=True)
            subprocess.run(['sudo', 'hciconfig', 'hci0', 'noscan'], check=True)
            time.sleep(1)
            subprocess.run(['sudo', 'hciconfig', 'hci0', 'piscan'], check=True)
            time.sleep(2)  # Added extra delay for stability
            logging.info("Bluetooth interface configured successfully")
        except subprocess.CalledProcessError as e:
            logging.error(f"Error configuring Bluetooth: {e}")
            raise

    def discover_scale(self):
        """Verify the scale is available"""
        for attempt in range(self.connection_retries):
            try:
                logging.info(f"Scanning for scale (attempt {attempt + 1})...")
                scanner = Scanner()
                devices = scanner.scan(5.0)
                
                for dev in devices:
                    if dev.addr.lower() == self.mac_address.lower():
                        logging.info(f"Found scale at address: {dev.addr}")
                        return True
                
                if attempt < self.connection_retries - 1:
                    logging.info(f"Scale not found, retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
            
            except Exception as e:
                logging.error(f"Error during discovery (attempt {attempt + 1}): {e}")
                if attempt < self.connection_retries - 1:
                    time.sleep(self.retry_delay)
        
        return False

    def read_weight(self):
        """Read weight from Bluetooth scale"""
        self.setup_bluetooth()
        
        # First ensure scale is discoverable
        if not self.discover_scale():
            raise Exception("Scale not found after all retries")

        for attempt in range(self.connection_retries):
            peripheral = None
            try:
                logging.info(f"Attempting to connect to scale at {self.mac_address}...")
                peripheral = Peripheral()
                peripheral.connect(self.mac_address)
                logging.info("Connected to scale")
                
                delegate = NotificationDelegate()
                peripheral.withDelegate(delegate)
                
                services = peripheral.getServices()
                for service in services:
                    characteristics = service.getCharacteristics()
                    for char in characteristics:
                        if char.uuid == self.NOTIFY_CHARACTERISTIC_UUID:
                            logging.info(f"Found notification characteristic: {char.uuid}")
                            peripheral.writeCharacteristic(char.valHandle + 1, b"\x01\x00")
                            logging.info("Enabled notifications")
                            break
                
                logging.info("Subscribed to notifications. Please step on the scale...")
                start_time = time.time()
                while time.time() - start_time < 30:  # 30 second timeout
                    if peripheral.waitForNotifications(1.0):
                        if delegate.weight_received:
                            return delegate.last_weight
                
                logging.error("Timeout waiting for weight measurement")
                
            except BTLEDisconnectError as e:
                logging.error(f"Connection attempt {attempt + 1} failed with disconnect: {e}")
                if attempt < self.connection_retries - 1:
                    logging.info(f"Retrying connection in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    raise
            except Exception as e:
                logging.error(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt < self.connection_retries - 1:
                    logging.info(f"Retrying connection in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    raise
            finally:
                if peripheral is not None:
                    try:
                        peripheral.disconnect()
                    except:
                        pass
        
        raise Exception("Failed to read weight from scale after all retries")


class SerialScale:
    """RS232 Scale Handler"""
    def __init__(self, device_id, port, baud_rate):
        self.port = port
        self.baud_rate = baud_rate
        self.serial = None
        self.device_id = device_id

    def __enter__(self):
        try:
            logging.info(f"Opening serial port {self.port} at {self.baud_rate} baud")
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                timeout=2,
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
        try:
            if not self.serial:
                raise Exception("Serial port not initialized")

            self.serial.reset_input_buffer()
            time.sleep(0.1)
            
            max_attempts = 5
            attempt = 0
            
            while attempt < max_attempts:
                if self.serial.in_waiting > 0:
                    raw_data = self.serial.readline()
                    
                    logging.info("=== Data Received ===")
                    logging.info(f"Raw (hex): {' '.join([f'{b:02x}' for b in raw_data])}")
                    logging.info(f"Raw (chr): {' '.join([chr(b) if 32 <= b <= 126 else '.' for b in raw_data])}")
                    
                    try:
                        data = raw_data.decode('ascii').strip()
                        logging.info(f"Decoded data: '{data}'")
                        
                        if data.startswith('sg') and data.endswith('kg'):
                            weight_str = data[2:-2]
                            sign = -1 if weight_str.startswith('-') else 1
                            weight_str = weight_str[1:] if sign == -1 else weight_str
                            weight = sign * Decimal(weight_str)
                            logging.info(f"Parsed weight: {weight}kg")
                            return {
                                self.device_id: {
                                    "scale_id": "scale-1",
                                    "wight": weight,
                                    "type": "RS232"
                                }
                            }
                        else:
                            logging.warning(f"Unexpected format: {data}")
                    except Exception as decode_error:
                        logging.error(f"Decoding error: {decode_error}")
                        
                attempt += 1
                time.sleep(0.5)
                
            raise Exception("No valid weight data received")
                
        except Exception as e:
            logging.error(f"Read error: {e}")
            raise

class IoTClient:
    """Handles communication with AWS IoT"""
    def __init__(self, device_id: str, endpoint: str, stage: str = STAGE):
        self.device_id = device_id
        self.endpoint = endpoint
        self.stage = stage
        self.mqtt_connection = self._create_mqtt_connection()
        
    def _create_mqtt_connection(self):
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
            client_id=f"device-{self.device_id}",
            clean_session=False,
            keep_alive_secs=30
        )
    
    def connect(self):
        connect_future = self.mqtt_connection.connect()
        connect_future.result(timeout=10)
        logging.info("Connected to AWS IoT")
    
    
    def save_measurement(self, weight, timestamp, uploaded=False):
        """Save measurement to local file"""
        measurement = {
            "weight": float(weight),
            "timestamp": timestamp,
            "unit": "kg",
            "uploaded": uploaded
        }
        
        # Create directory if it doesn't exist
        os.makedirs("/tmp/measurements", exist_ok=True)
        
        # Save measurement with timestamp as filename
        filename = f"/tmp/measurements/{timestamp.replace(':', '-')}.json"
        with open(filename, 'w') as f:
            json.dump(measurement, f)
    def publish_measurement(self, weight: Decimal):
        try:
            topic = f"{self.stage}/{self.stage}/scale-measurements"
            timestamp = datetime.utcnow().isoformat() + 'Z'
            
            message = {
                'measurement_id': f"scale-1-{int(time.time())}",
                'device_id': self.device_id,
                'scale_id': self.device_id,
                'weight': float(weight),
                'timestamp': timestamp,
                'unit': 'kg'
            }
            
            logging.info(f"Publishing message to topic '{topic}': {json.dumps(message, indent=2)}")
            
            future, _ = self.mqtt_connection.publish(
                topic=topic,
                payload=json.dumps(message),
                qos=mqtt.QoS.AT_LEAST_ONCE
            )
            
            future.result(timeout=10)
            logging.info("Measurement published successfully")
            
            # Save local copy
            os.makedirs("/tmp/measurements", exist_ok=True)
            filename = f"/tmp/measurements/{timestamp.replace(':', '-')}.json"
            with open(filename, 'w') as f:
                json.dump(message, f)
            logging.info(f"Measurement saved to {filename}")
                
        except Exception as e:
            logging.error(f"Error publishing measurement: {e}")
            raise

    def disconnect(self):
        try:
            disconnect_future = self.mqtt_connection.disconnect()
            disconnect_future.result(timeout=10)
            logging.info("Disconnected from AWS IoT")
        except Exception as e:
            logging.error(f"Error disconnecting: {e}")


def main():
    """Main function with device type selection"""
    parser = argparse.ArgumentParser(description='Scale Reader')
    parser.add_argument('--device', 
                      choices=['rs232', 'bluetooth'],
                      required=False,
                      help='Device type to use (rs232 or bluetooth)')

    args = parser.parse_args()
    
    try:
        setup_logging()
        logging.info(f"Starting measurement process using {args.device} device")
        
        # Load configuration
        config = ScaleConfig(args.device)
        logging.info("Configuration loaded successfully")
        
        # Initialize IoT client
        iot_client = IoTClient(config.data['device_id'], config.data['iot_endpoint'])
        logging.info("IoT client initialized")
        
        # Connect to AWS IoT
        iot_client.connect()
        logging.info("Connected to AWS IoT")
        
        try:
            # Choose device type based on argument
            if args.device == 'rs232' or config.data["connection_type"] == 'rs232':
                with SerialScale(config.data['device_id'], 
                               config.data['serial_port'], 
                               config.data['baud_rate']) as scale:
                    weights = scale.read_weight()
            else:  # bluetooth
                scale = BluetoothScale(config.data['device_id'], 
                                     config.data['bluetooth_mac'])
                weights = scale.read_weight()
            
            # Process weights
            for scale_id, weight in weights.items():
                iot_client.publish_measurement(weight["wight"])
                logging.info(f"Measurement taken and published successfully from {config.data['connection_type']} device")
                
        finally:
            iot_client.disconnect()

    except Exception as e:
        logging.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
