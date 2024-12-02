#!/usr/bin/env python3
from bluepy.btle import Scanner, DefaultDelegate
from flask import Flask, jsonify, render_template, request, send_from_directory
import subprocess
import logging
import os
import json
import time
from datetime import datetime
from typing import List, Dict, Tuple
from werkzeug.utils import secure_filename
import queue
import threading

# Constants
LOG_PATH = '/var/log/scale-reader/web.log'
WPA_SUPPLICANT_PATH = '/etc/wpa_supplicant/wpa_supplicant.conf'
CONFIG_PATH = '/home/amitash/certs/config.json'
CERT_UPLOAD_DIR = '/home/amitash/certs'
REQUIRED_CERTS = ['device.cert.pem', 'device.private.key', 'root-CA.crt', 'config.json']

# Configure logging
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

installation_logs = queue.Queue()

def log_to_window(message, level="INFO"):
    """Add a log message to the installation_logs queue"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    installation_logs.put({
        'timestamp': timestamp,
        'source': 'install',
        'level': level,
        'message': message.strip()
    })
    # Also log to file
    logging.log(
        logging.INFO if level == "INFO" else logging.ERROR,
        f"[Installation] {message.strip()}"
    )

def process_output(pipe, is_error=False):
    """Process output from subprocess pipe"""
    for line in iter(pipe.readline, ''):
        if line:
            log_to_window(line, "ERROR" if is_error else "INFO")


# Add console logging for debugging
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logging.getLogger().addHandler(console_handler)


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
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Error resetting Bluetooth interface: {e}")
        return False

class ScanDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)

    def handleDiscovery(self, dev, isNewDev, isNewData):
        if isNewDev:
            logging.info(f"Discovered device {dev.addr}")

    
# Create Flask app
app = Flask(__name__, 
    template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'),
    static_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
)

def set_config(config):
    """Set scale configuration"""
    try:
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f)
            logging.info(f"Configuration saved: {config}")
    except Exception as e:
        logging.error(f"Error saving configuration: {e}")

def get_config() -> Dict[str, str]:
    """Get scale configuration"""
    try:
        if not os.path.exists(CONFIG_PATH):
            logging.warning(f"Config file not found at {CONFIG_PATH}")
            return {}
            
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
            # Remove sensitive information
            logging.info(f"Configuration read successfully: {config}")
            if 'id_token' in config:
                del config['id_token']
            return config
    except Exception as e:
        logging.error(f"Error reading config: {e}")
        return {}

def scan_networks() -> List[Dict[str, str]]:
    """Scan for available WiFi networks"""
    try:
        # Scan for networks
        subprocess.run(['iwlist', 'wlan0', 'scan'], capture_output=True)
        result = subprocess.run(
            ['iwlist', 'wlan0', 'scan'], 
            capture_output=True, 
            text=True
        )
        
        networks = []
        current_network = {}
        
        for line in result.stdout.split('\n'):
            line = line.strip()
            
            if 'ESSID:' in line:
                ssid = line.split('ESSID:')[1].strip('"')
                if ssid and current_network:
                    current_network['ssid'] = ssid
                    networks.append(current_network)
                    current_network = {}
                elif ssid:
                    current_network = {'ssid': ssid}
                    
            elif 'Quality=' in line:
                try:
                    quality = line.split('Quality=')[1].split(' ')[0]
                    level = int(quality.split('/')[0]) / int(quality.split('/')[1]) * 100
                    current_network['signal_strength'] = round(level)
                except:
                    current_network['signal_strength'] = 0
        
        # Remove duplicates and sort by signal strength
        unique_networks = {network['ssid']: network for network in networks}.values()
        return sorted(unique_networks, key=lambda x: x['signal_strength'], reverse=True)
        
    except Exception as e:
        logging.error(f"Error scanning networks: {e}")
        return []

def get_wifi_status() -> Tuple[bool, str, str]:
    """Get current WiFi connection status"""
    try:
        result = subprocess.run(
            ['iwgetid', 'wlan0', '-r'], 
            capture_output=True, 
            text=True
        )
        
        if result.returncode == 0 and result.stdout.strip():
            ssid = result.stdout.strip()
            ip_result = subprocess.run(
                ['ip', 'addr', 'show', 'wlan0'], 
                capture_output=True, 
                text=True
            )
            ip_address = "Unknown"
            for line in ip_result.stdout.split('\n'):
                if 'inet ' in line:
                    ip_address = line.split()[1].split('/')[0]
                    break
            
            logging.info(f"WiFi Status - Connected to {ssid} with IP {ip_address}")
            return True, ssid, ip_address
            
        logging.info("WiFi Status - Not connected")
        return False, "", ""
    except Exception as e:
        logging.error(f"Error getting WiFi status: {e}")
        return False, "", ""

def connect_to_network(ssid: str, password: str) -> Tuple[bool, str]:
    """Connect to a WiFi network"""
    try:
        logging.info(f"Attempting to connect to network: {ssid}")
        
        # First disconnect from any existing connection
        result = subprocess.run(
            ['sudo', '/bin/bash', '/usr/local/bin/wifi-disconnect.sh', '-i', 'wlan0'],
            capture_output=True,
            text=True
        )
        time.sleep(2)
        
        # Connect using the script
        result = subprocess.run(
            ['sudo', '/bin/bash', '/usr/local/bin/connect_to_wifi.sh',
             '-i', 'wlan0',
             '-s', ssid,
             '-p', password],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            logging.info(f"Successfully connected to {ssid}")
            
            # Store successful connection
            wifi_store_dir = '/etc/scale-reader/wifi'
            os.makedirs(wifi_store_dir, exist_ok=True)
            
            with open(f'{wifi_store_dir}/last_connection.conf', 'w') as f:
                f.write(f'SSID="{ssid}"\n')
                f.write(f'PASSWORD="{password}"\n')
            
            os.chmod(f'{wifi_store_dir}/last_connection.conf', 0o600)
            
            return True, ""
        else:
            error_msg = f"Failed to connect: {result.stderr}"
            logging.error(error_msg)
            return False, error_msg
            
    except Exception as e:
        error_msg = f"Error connecting to network: {str(e)}"
        logging.error(error_msg)
        return False, error_msg

def disconnect_wifi() -> Tuple[bool, str]:
    """Disconnect from WiFi network"""
    try:
        logging.info("Initiating WiFi disconnect")
        # Remove stored credentials
        try:
            os.remove('/etc/scale-reader/wifi/last_connection.conf')
        except FileNotFoundError:
            pass
            
        result = subprocess.run(
            ['sudo', '/bin/bash', '/usr/local/bin/wifi-disconnect.sh', '-i', 'wlan0'],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            logging.info("Successfully disconnected from WiFi")
            return True, ""
        
        error_msg = result.stderr
        logging.error(f"Failed to disconnect: {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = str(e)
        logging.error(f"Error disconnecting WiFi: {error_msg}")
        return False, error_msg

@app.route('/')
def index():
    """Serve the main page"""
    logging.info("Serving main page")
    return render_template('index.html')

@app.route('/api/config')
def config():
    """Get scale configuration"""
    logging.info("Getting configuration")
    return jsonify(get_config())

@app.route('/api/status')
def status():
    """Get current WiFi status"""
    connected, ssid, ip = get_wifi_status()
    logging.info(f"Status check - Connected: {connected}, SSID: {ssid}, IP: {ip}")
    return jsonify({
        'connected': connected,
        'ssid': ssid,
        'ip': ip
    })

@app.route('/api/scan')
def scan():
    """Scan for available networks"""
    logging.info("Starting network scan")
    networks = scan_networks()
    logging.info(f"Network scan complete - found {len(networks)} networks")
    return jsonify({'networks': networks})

@app.route('/api/connect', methods=['POST'])
def connect():
    """Connect to a network"""
    data = request.get_json()
    if not data or 'ssid' not in data or 'password' not in data:
        logging.error("Missing required fields in connect request")
        return jsonify({'success': False, 'error': 'Missing required fields'})
    
    logging.info(f"Attempting to connect to network: {data['ssid']}")
    success, error = connect_to_network(data['ssid'], data['password'])
    return jsonify({
        'success': success,
        'error': error
    })

@app.route('/api/disconnect')
def disconnect():
    """Disconnect from current network"""
    logging.info("Disconnecting from WiFi")
    success, error = disconnect_wifi()
    return jsonify({
        'success': success,
        'error': error
    })

@app.route('/api/sampling-interval', methods=['GET', 'POST'])
def sampling_interval():
    """Get or set sampling interval"""
    try:
        if request.method == 'GET':
            # Read current interval config
            try:
                with open('/etc/scale-reader/interval.json', 'r') as f:
                    config = json.load(f)
                    return jsonify({
                        'success': True,
                        'seconds': config['seconds'],
                        'rate': config['interval']
                    })
            except FileNotFoundError:
                return jsonify({
                    'success': True,
                    'seconds': 1800,
                    'rate': 'SLOW'
                })
            
        else:  # POST
            data = request.get_json()
            if 'rate' not in data:
                return jsonify({
                    'success': False,
                    'error': 'Missing rate parameter'
                })
            
            rate = data['rate'].upper()
            if rate not in ['FAST', 'SLOW']:
                return jsonify({
                    'success': False,
                    'error': 'Rate must be FAST or SLOW'
                })
            
            # Run scale-interval script
            cmd = ['--fast'] if rate == 'FAST' else ['--slow']
            result = subprocess.run(
                ['python', '/home/amitash/set_scale_interval.py'] + cmd,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                return jsonify({
                    'success': True,
                    'message': f'Sampling rate set to {rate}'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': f'Failed to update interval: {result.stderr}'
                })
                
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })
        
@app.route('/api/check-certificates')
def check_certificates():
    """Check if all required certificates are present"""
    try:
        missing_certs = []
        found_certs = []
        
        for cert in REQUIRED_CERTS:
            cert_path = os.path.join(CERT_UPLOAD_DIR, cert)
            if not os.path.exists(cert_path):
                missing_certs.append(cert)
            else:
                found_certs.append(cert)
        
        return jsonify({
            'success': True,
            'complete': len(missing_certs) == 0,
            'found': found_certs,
            'missing': missing_certs
        })
    except Exception as e:
        logging.error(f"Error checking certificates: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

    
@app.route('/api/upload-certificates', methods=['POST'])
def upload_certificates():
    """Handle certificate file uploads"""
    try:
        if 'certificates' not in request.files:
            logging.error("No files in certificate upload request")
            return jsonify({
                'success': False,
                'message': 'No files uploaded'
            })

        files = request.files.getlist('certificates')
        uploaded_files = [f.filename for f in files]
        logging.info(f"Received certificate files: {', '.join(uploaded_files)}")
        
        # Verify all required certificates are present
        missing_certs = [cert for cert in REQUIRED_CERTS 
                        if cert not in uploaded_files]
        
        if missing_certs:
            missing_msg = f"Missing required certificates: {', '.join(missing_certs)}"
            logging.error(missing_msg)
            return jsonify({
                'success': False,
                'message': missing_msg
            })

        # Create certificates directory if it doesn't exist
        os.makedirs(CERT_UPLOAD_DIR, exist_ok=True)

        # Save files
        for file in files:
            if file.filename in REQUIRED_CERTS:
                filename = secure_filename(file.filename)
                filepath = os.path.join(CERT_UPLOAD_DIR, filename)
                file.save(filepath)
                # Set proper permissions
                os.chmod(filepath, 0o600)
                os.chown(filepath, 0, 0)  # root:root
                logging.info(f"Saved certificate: {filename}")

        return jsonify({
            'success': True,
            'message': 'Certificates uploaded successfully'
        })

    except Exception as e:
        error_msg = f"Error uploading certificates: {str(e)}"
        logging.error(error_msg)
        return jsonify({
            'success': False,
            'message': error_msg
        })

@app.route('/api/install-services', methods=['POST'])
def install_services():
    """Install and configure required services"""
    try:
        log_to_window("Starting service installation")
        
        # Get configuration parameters from request
        data = request.get_json()
        logging.info(f"Received configuration data: {data}")
        if not data:
            log_to_window("No configuration data provided", "ERROR")
            return jsonify({
                'success': False,
                'message': 'No configuration data provided'
            })
        config = get_config()
        config['connection_type'] = data.get('connection_type', 'rs232')
        config['bluetooth_mac'] = data.get('bluetooth_mac', '00:00:00:00:00:00')
        set_config(config)
        # Extract parameters with defaults
        device_id = data.get('device_id')
        if not device_id:
            log_to_window("Scale ID is required", "ERROR")
            return jsonify({
                'success': False,
                'message': 'Scale ID is required'
            })
            
        serial_port = data.get('serial_port', '/dev/ttyUSB0')
        baud_rate = data.get('baud_rate', 1200)
        endpoint = data.get('endpoint', 'alyu5ve98pej6.iot.us-east-1.amazonaws.com')
        
        # Log configuration
        log_to_window(f"Configuration received:")
        log_to_window(f"Scale ID: {device_id}")
        log_to_window(f"Serial Port: {serial_port}")
        log_to_window(f"Baud Rate: {baud_rate}")
        log_to_window(f"IoT Endpoint: {endpoint}")
        
        # Create temporary script to handle user input
        setup_script = f'''#!/bin/bash
echo "{device_id}"  # Scale ID
echo "{serial_port}"  # Serial Port
echo "{baud_rate}"  # Baud Rate
echo "{endpoint}"  # IoT Endpoint
'''
        
        with open('/tmp/setup_input.sh', 'w') as f:
            f.write(setup_script)
        os.chmod('/tmp/setup_input.sh', 0o755)
        
        # Execute the setup script
        log_to_window("Executing setup script...")
        
        # Build the command with full paths
        setup_cmd = [
            'sudo', '/bin/bash', '/usr/local/bin/rpi_setup_wo_wifi.sh'
        ]
        
        # Run the script with input piped from our temporary script
        process = subprocess.Popen(
            setup_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Create threads to handle stdout and stderr
        stdout_thread = threading.Thread(
            target=process_output, 
            args=(process.stdout,)
        )
        stderr_thread = threading.Thread(
            target=process_output, 
            args=(process.stderr, True)
        )
        
        # Start threads
        stdout_thread.start()
        stderr_thread.start()
        
        # Write inputs to process
        process.stdin.write(f"{device_id}\n")
        process.stdin.write(f"{serial_port}\n")
        process.stdin.write(f"{baud_rate}\n")
        process.stdin.write(f"{endpoint}\n")
        process.stdin.flush()
        
        # Wait for process to complete
        return_code = process.wait()
        
        # Wait for output threads to complete
        stdout_thread.join()
        stderr_thread.join()
        
        # Clean up
        process.stdout.close()
        process.stderr.close()
        process.stdin.close()
        
        # Clean up temporary script
        os.remove('/tmp/setup_input.sh')
        
        if return_code != 0:
            log_to_window("Setup script failed", "ERROR")
            return jsonify({
                'success': False,
                'message': 'Setup failed'
            })
        
        log_to_window("Service installation completed successfully")
        return jsonify({
            'success': True,
            'message': 'Services installed and configured successfully'
        })

    except Exception as e:
        error_msg = f"Error installing services: {str(e)}"
        log_to_window(error_msg, "ERROR")
        return jsonify({
            'success': False,
            'message': error_msg
        })

@app.route('/api/installation-logs')
def get_installation_logs():
    """Get any new installation logs"""
    logs = []
    while not installation_logs.empty():
        try:
            logs.append(installation_logs.get_nowait())
        except queue.Empty:
            break
    return jsonify({'logs': logs})


@app.route('/api/logs')
def get_logs():
    """Get recent logs"""
    try:
        # Read both system logs and application logs
        logs = []
        
        # Get WiFi manager service logs from journalctl
        try:
            result = subprocess.run(
                ['journalctl', '-u', 'wifi-manager', '-n', '50', '--no-pager', '--output=short'],
                capture_output=True,
                text=True
            )
            if result.stdout:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        logs.append({
                            'timestamp': ' '.join(line.split()[:3]),
                            'source': 'system',
                            'message': ' '.join(line.split()[3:])
                        })
        except Exception as e:
            logging.error(f"Error reading system logs: {e}")

        # Get application logs
        try:
            if os.path.exists(LOG_PATH):
                with open(LOG_PATH, 'r') as f:
                    app_logs = f.readlines()[-50:]  # Get last 50 lines
                    for line in app_logs:
                        try:
                            # Parse the log line (assuming standard format)
                            parts = line.split(' - ', 3)
                            if len(parts) >= 3:
                                timestamp = parts[0]
                                message = ' - '.join(parts[2:])
                                logs.append({
                                    'timestamp': timestamp,
                                    'source': 'app',
                                    'message': message.strip()
                                })
                        except Exception as parse_error:
                            logging.error(f"Error parsing log line: {parse_error}")
                            continue
        except Exception as e:
            logging.error(f"Error reading application logs: {e}")

        # Sort logs by timestamp (roughly)
        logs.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Add some test logs if no logs are found
        if not logs:
            logs.append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'source': 'app',
                'message': 'Log system initialized'
            })

        return jsonify({
            'success': True,
            'logs': logs[:50]  # Return most recent 50 entries
        })
    except Exception as e:
        logging.error(f"Error getting logs: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/measurements')
def get_measurements():
    """Get measurements from /tmp/measurements directory"""
    try:
        measurements_dir = "/tmp/measurements"
        measurements = []

        if os.path.exists(measurements_dir):
            # Read all JSON files in the directory
            for filename in sorted(os.listdir(measurements_dir), reverse=True):
                if filename.endswith('.json'):
                    filepath = os.path.join(measurements_dir, filename)
                    try:
                        with open(filepath, 'r') as f:
                            measurement = json.load(f)
                            measurements.append(measurement)
                    except Exception as e:
                        logging.error(f"Error reading measurement file {filepath}: {e}")
                        continue

        # Sort measurements by timestamp, most recent first
        measurements.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify({
            'success': True,
            'measurements': measurements[:10]  # Return only the 10 most recent
        })
        
    except Exception as e:
        logging.error(f"Error getting measurements: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/scan-bluetooth', methods=['GET'])
def scan_bluetooth():
    try:
        # Setup Bluetooth first
        if not setup_bluetooth():
            return jsonify({
                "success": False,
                "message": "Failed to initialize Bluetooth interface"
            })

        # Create scanner with delegate
        scanner = Scanner().withDelegate(ScanDelegate())
        
        # Perform scan
        logging.info("Starting Bluetooth scan...")
        devices = scanner.scan(10.0)  # Increase scan time to 10 seconds
        
        # Process results
        device_list = []
        for dev in devices:
            device_info = {
                "address": dev.addr,
                "name": None,
                "rssi": dev.rssi,
                "scanData": []
            }
            
            # Get all scan data
            for (adtype, desc, value) in dev.getScanData():
                device_info["scanData"].append({
                    "type": adtype,
                    "desc": desc,
                    "value": value
                })
                if desc == "Complete Local Name":
                    device_info["name"] = value
            
            # Only attempt connection if no name found and it looks like a scale
            if device_info["name"] is None:
                try:
                    from bluepy.btle import Peripheral, BTLEDisconnectError
                    import socket
                    
                    # Set socket timeout
                    socket.setdefaulttimeout(3)
                    
                    # Attempt connection with timeout
                    periph = Peripheral(dev.addr, timeout=3)
                    try:
                        chars = periph.getCharacteristics(uuid=0x2A00)
                        if chars:
                            device_info["name"] = chars[0].read().decode()
                    except (BTLEDisconnectError, AttributeError) as e:
                        logging.debug(f"Could not read characteristic from {dev.addr}: {e}")
                    finally:
                        try:
                            periph.disconnect()
                        except:
                            pass
                except Exception as e:
                    logging.debug(f"Failed to connect to {dev.addr}: {e}")
            
            device_list.append(device_info)
        
        # Filter for likely scale devices (SH2492) but also include devices
        # that might be scales based on other characteristics
        scale_devices = []
        for device in device_list:
            is_scale = False
            
            # Check name for scale indicators
            if device["name"] and any(indicator in device["name"].upper() 
                                    for indicator in ["SH2492", "SCALE", "WEIGHT"]):
                is_scale = True
                
            # Check manufacturer data
            for scan_data in device["scanData"]:
                if scan_data["desc"] == "Manufacturer" and "2492" in scan_data["value"]:
                    is_scale = True
                    
            if is_scale:
                scale_devices.append({
                    "address": device["address"],
                    "name": device["name"] or "Unknown Scale Device",
                    "rssi": device["rssi"]
                })
        
        logging.info(f"Scan complete. Found {len(scale_devices)} potential scale devices")
        
        return jsonify({
            "success": True,
            "devices": scale_devices
        })
        
    except Exception as e:
        logging.error(f"Error during Bluetooth scan: {e}")
        return jsonify({
            "success": False,
            "message": str(e)
        })
                            
if __name__ == '__main__':
    try:
        # Ensure log directory exists
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        
        # Log startup information
        logging.info("Starting WiFi Manager service")
        logging.info(f"Template directory: {app.template_folder}")
        logging.info(f"Static directory: {app.static_folder}")
        
        # Check if template exists
        template_path = os.path.join(app.template_folder, 'index.html')
        if os.path.exists(template_path):
            logging.info(f"Template file exists at {template_path}")
        else:
            logging.error(f"Template file not found at {template_path}")

        # Run the server
        app.run(host='0.0.0.0', port=80, debug=True)
    except Exception as e:
        logging.error(f"Fatal error during startup: {str(e)}")
        raise