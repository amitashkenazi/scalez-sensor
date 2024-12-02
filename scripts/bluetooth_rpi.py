#!/usr/bin/env python3

from bluepy.btle import Scanner, DefaultDelegate, Peripheral, BTLEDisconnectError
import struct
import logging
from datetime import datetime
import json
import os
import time
import subprocess

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/scale_ble.log'),
        logging.StreamHandler()
    ]
)

class NotificationDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)
        self.last_weight = None
        self.weight_received = False

    def handleNotification(self, cHandle, data):
        try:
            logging.info(f"Received data: {data.hex()}")
            logging.info("Data bytes: " + " ".join([f"{b:02x}" for b in data]))
            
            # Decode the ASCII data
            text_data = data.decode('ascii').strip()
            logging.info(f"Decoded text: {text_data}")
            
            # Extract weight value - format is "sg0000.00kg"
            if text_data.startswith('sg') and text_data.endswith('kg'):
                weight_str = text_data[2:-2]  # Remove 'sg' and 'kg'
                self.last_weight = float(weight_str)
                logging.info(f"Parsed weight: {self.last_weight} kg")
                self.weight_received = True
        except Exception as e:
            logging.error(f"Error parsing notification: {e}")

def setup_bluetooth():
    """Initialize Bluetooth on Raspberry Pi"""
    try:
        # Reset bluetooth interface
        subprocess.run(['sudo', 'hciconfig', 'hci0', 'down'], check=True)
        time.sleep(1)
        subprocess.run(['sudo', 'hciconfig', 'hci0', 'up'], check=True)
        time.sleep(1)
        # Set LE scan parameters
        subprocess.run(['sudo', 'hciconfig', 'hci0', 'leadv', '0'], check=True)
        subprocess.run(['sudo', 'hciconfig', 'hci0', 'noscan'], check=True)
        time.sleep(1)
        subprocess.run(['sudo', 'hciconfig', 'hci0', 'piscan'], check=True)
        logging.info("Bluetooth interface reset and configured successfully")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error resetting Bluetooth interface: {e}")
        raise

class SH2492Scale:
    def __init__(self):
        self.NOTIFY_CHARACTERISTIC_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
        self.SCALE_MAC = "98:da:20:07:e1:8b"  # Your scale's MAC address
        self.connection_retries = 3
        self.retry_delay = 2

    def discover_scale(self):
        """Verify the scale is available"""
        for attempt in range(self.connection_retries):
            try:
                logging.info(f"Scanning for scale (attempt {attempt + 1})...")
                scanner = Scanner()
                devices = scanner.scan(5.0)
                
                for dev in devices:
                    if dev.addr.lower() == self.SCALE_MAC.lower():
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

    def connect_and_wait_for_weight(self, timeout=30):
        """Connect to scale and wait for weight measurement"""
        for attempt in range(self.connection_retries):
            peripheral = None
            try:
                logging.info(f"Attempting to connect to scale at {self.SCALE_MAC}...")
                peripheral = Peripheral()
                peripheral.connect(self.SCALE_MAC)
                logging.info("Connected to scale")
                
                # Setup notification delegate
                delegate = NotificationDelegate()
                peripheral.withDelegate(delegate)
                
                # Find the characteristic
                services = peripheral.getServices()
                for service in services:
                    characteristics = service.getCharacteristics()
                    for char in characteristics:
                        if char.uuid == self.NOTIFY_CHARACTERISTIC_UUID:
                            logging.info(f"Found notification characteristic: {char.uuid}")
                            # Enable notifications
                            peripheral.writeCharacteristic(char.valHandle + 1, b"\x01\x00")
                            logging.info("Enabled notifications")
                            break
                
                logging.info("Subscribed to notifications. Please step on the scale...")
                
                # Wait for weight measurement
                start_time = time.time()
                while time.time() - start_time < timeout:
                    if peripheral.waitForNotifications(1.0):
                        if delegate.weight_received:
                            return delegate.last_weight
                
                logging.error("Timeout waiting for weight measurement")
                return None
                
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

def save_measurement(weight: float, timestamp: str) -> None:
    """Save measurement to local file"""
    measurement = {
        "weight": weight,
        "timestamp": timestamp,
        "unit": "kg",
    }
    
    os.makedirs("/tmp/measurements", exist_ok=True)
    filename = f"/tmp/measurements/{timestamp.replace(':', '-')}.json"
    
    with open(filename, 'w') as f:
        json.dump(measurement, f)
    logging.info(f"Measurement saved to {filename}")

def main():
    try:
        # Setup Bluetooth
        setup_bluetooth()
        time.sleep(2)  # Wait for Bluetooth to stabilize
        
        scale = SH2492Scale()
        
        # Discover scale
        if not scale.discover_scale():
            logging.error("Scale not found after all retries")
            return 1
        
        # Connect and wait for weight
        logging.info("Connecting to scale. Please step on the scale when ready...")
        weight = scale.connect_and_wait_for_weight()
        
        if weight is not None:
            timestamp = datetime.utcnow().isoformat() + 'Z'
            save_measurement(weight, timestamp)
            logging.info(f"Final weight reading: {weight} kg")
        
    except Exception as e:
        logging.error(f"Error in main: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    main()