#!/usr/bin/env python3

import os
import sys
import json
import argparse
import subprocess
import logging
from pathlib import Path

# Constants
SERVICE_NAME = "scale-reader.service"
INTERVAL_CONFIG_PATH = "/etc/scale-reader/interval.json"

def setup_logging():
    """Configure logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def load_config():
    """Load current configuration"""
    try:
        if os.path.exists(INTERVAL_CONFIG_PATH):
            with open(INTERVAL_CONFIG_PATH, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {"interval": "SLOW", "minutes": 30}

def save_config(interval_type, seconds):
    """Save current configuration"""
    os.makedirs(os.path.dirname(INTERVAL_CONFIG_PATH), exist_ok=True)
    with open(INTERVAL_CONFIG_PATH, 'w') as f:
        json.dump({
            "interval": interval_type,
            "seconds": seconds
        }, f, indent=2)

def update_service_timer(seconds):
    """Update the service RestartSec parameter"""
    try:
        # Create override directory if it doesn't exist
        os.makedirs("/etc/systemd/system/scale-reader.service.d", exist_ok=True)
        
        # Create override file
        override_content = f"""[Service]
RestartSec={seconds}"""
        
        with open("/etc/systemd/system/scale-reader.service.d/override.conf", "w") as f:
            f.write(override_content)
        
        # Reload systemd and restart service
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "restart", SERVICE_NAME], check=True)
        return True
    except Exception as e:
        logging.error(f"Failed to update service: {e}")
        return False

def main():
    """Main function"""
    setup_logging()
    
    parser = argparse.ArgumentParser(description='Set scale reader sampling interval')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--fast', action='store_true', help='Set to fast mode (60 seconds)')
    group.add_argument('--slow', action='store_true', help='Set to slow mode (1800 seconds)')
    group.add_argument('--seconds', type=int, help='Set custom interval in seconds')
    
    args = parser.parse_args()
    
    # Determine interval
    if args.fast:
        interval_type = "FAST"
        seconds = 60
    elif args.slow:
        interval_type = "SLOW"
        seconds = 1800
    else:
        if args.seconds < 10 or args.seconds > 86400:
            logging.error("Interval must be between 10 and 86400 seconds")
            sys.exit(1)
        interval_type = "CUSTOM"
        seconds = args.seconds
    
    # Update service
    if update_service_timer(seconds):
        # Save configuration
        save_config(interval_type, seconds)
        logging.info(f"Successfully set sampling interval to {interval_type} ({seconds} seconds)")
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    if os.geteuid() != 0:
        logging.error("This script must be run as root")
        sys.exit(1)
    main()