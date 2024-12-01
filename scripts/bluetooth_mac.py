#!/usr/bin/env python3

import asyncio
from bleak import BleakClient, BleakScanner
import struct
import logging
from datetime import datetime
import json
import os
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/scale_ble.log'),
        logging.StreamHandler()
    ]
)

class SH2492Scale:
    def __init__(self):
        self.CUSTOM_SERVICE_UUID = "FFE0"
        self.NOTIFY_CHARACTERISTIC_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
        self.device = None
        self.client = None
        self.SCALE_NAME = "SH2492"
        self.weight_event = asyncio.Event()
        self.last_weight = None

    def notification_handler(self, sender, data):
        """Handle incoming notifications from the scale"""
        try:
            logging.info(f"Received data: {data.hex()}")
            logging.info("Data bytes: " + " ".join([f"{b:02x}" for b in data]))
            
            # Decode the ASCII data
            text_data = data.decode('ascii').strip()
            logging.info(f"Decoded text: {text_data}")
            
            # Extract weight value - format is "sg0000.00kg"
            if text_data.startswith('sg') and text_data.endswith('kg'):
                weight_str = text_data[2:-2]  # Remove 'sg' and 'kg'
                weight = float(weight_str)
                logging.info(f"Parsed weight: {weight} kg")
                
                self.last_weight = weight
                self.weight_event.set()
        except Exception as e:
            logging.error(f"Error parsing notification: {e}")

    async def discover_scale(self):
        """Scan for and find the SH2492 scale"""
        logging.info("Scanning for SH2492 scale...")
        devices = await BleakScanner.discover()
        
        for device in devices:
            logging.info(f"Found device: {device.name} ({device.address})")
            if device.name and self.SCALE_NAME in device.name:
                self.device = device
                logging.info(f"Found scale: {device.name}")
                return True
        return False

    async def connect_and_wait_for_weight(self, timeout=30):
        """Connect to scale and wait for weight measurement"""
        if not self.device:
            raise Exception("Scale not found")
            
        async with BleakClient(self.device.address) as self.client:
            logging.info(f"Connected to {self.device.name}")
            
            # Subscribe to notifications
            await self.client.start_notify(
                self.NOTIFY_CHARACTERISTIC_UUID, 
                self.notification_handler
            )
            
            logging.info("Subscribed to notifications. Please step on the scale...")
            
            # Wait for weight measurement or timeout
            try:
                await asyncio.wait_for(self.weight_event.wait(), timeout)
                return self.last_weight
            except asyncio.TimeoutError:
                logging.error("Timeout waiting for weight measurement")
                return None
            finally:
                await self.client.stop_notify(self.NOTIFY_CHARACTERISTIC_UUID)

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

async def main():
    try:
        scale = SH2492Scale()
        
        # Discover scale
        if not await scale.discover_scale():
            logging.error("SH2492 scale not found")
            return 1
        
        # Connect and wait for weight
        logging.info("Connecting to scale. Please step on the scale when ready...")
        weight = await scale.connect_and_wait_for_weight()
        
        if weight is not None:
            timestamp = datetime.utcnow().isoformat() + 'Z'
            save_measurement(weight, timestamp)
            logging.info(f"Final weight reading: {weight} kg")
        
    except Exception as e:
        logging.error(f"Error in main: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    asyncio.run(main())