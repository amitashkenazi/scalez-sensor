#!/usr/bin/env python3

from flask import Flask, jsonify, render_template, request, send_from_directory
import subprocess
import logging
import os
import json
import time
from typing import List, Dict, Tuple
from werkzeug.utils import secure_filename

# Constants
LOG_PATH = '/var/log/scale-reader/web.log'
WPA_SUPPLICANT_PATH = '/etc/wpa_supplicant/wpa_supplicant.conf'
CONFIG_PATH = '/etc/scale-reader/config.json'
CERT_UPLOAD_DIR = '/etc/scale-reader/certs'
REQUIRED_CERTS = ['device.cert.pem', 'device.private.key', 'root-CA.crt']

# Configure logging
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Create Flask app
app = Flask(__name__, 
    static_folder='static',
    template_folder='templates'
)

def get_config() -> Dict[str, str]:
    """Get scale configuration"""
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
            # Remove sensitive information
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
            
            return True, ssid, ip_address
            
        return False, "", ""
    except Exception as e:
        logging.error(f"Error getting WiFi status: {e}")
        return False, "", ""

@app.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')

@app.route('/api/config')
def config():
    """Get scale configuration"""
    return jsonify(get_config())

@app.route('/api/status')
def status():
    """Get current WiFi status"""
    connected, ssid, ip = get_wifi_status()
    return jsonify({
        'connected': connected,
        'ssid': ssid,
        'ip': ip
    })

@app.route('/api/scan')
def scan():
    """Scan for available networks"""
    networks = scan_networks()
    return jsonify({'networks': networks})

@app.route('/api/connect', methods=['POST'])
def connect():
    """Connect to a network"""
    data = request.get_json()
    if not data or 'ssid' not in data or 'password' not in data:
        return jsonify({'success': False, 'error': 'Missing required fields'})
    
    try:
        result = subprocess.run(
            ['sudo', '/bin/bash', '/usr/local/bin/connect_to_wifi.sh',
             '-i', 'wlan0',
             '-s', data['ssid'],
             '-p', data['password']],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': result.stderr})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/disconnect')
def disconnect():
    """Disconnect from current network"""
    try:
        result = subprocess.run(
            ['sudo', '/bin/bash', '/usr/local/bin/wifi-disconnect.sh', '-i', 'wlan0'],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': result.stderr})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/upload-certificates', methods=['POST'])
def upload_certificates():
    """Handle certificate file uploads"""
    try:
        if 'certificates' not in request.files:
            return jsonify({
                'success': False,
                'message': 'No files uploaded'
            })

        files = request.files.getlist('certificates')
        uploaded_files = [f.filename for f in files]
        
        # Verify all required certificates are present
        missing_certs = [cert for cert in REQUIRED_CERTS 
                        if cert not in uploaded_files]
        
        if missing_certs:
            return jsonify({
                'success': False,
                'message': f'Missing required certificates: {", ".join(missing_certs)}'
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

        return jsonify({
            'success': True,
            'message': 'Certificates uploaded successfully'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error uploading certificates: {str(e)}'
        })

@app.route('/api/install-services', methods=['POST'])
def install_services():
    """Install and configure required services"""
    try:
        # Create necessary directories
        os.makedirs('/var/log/scale-reader', exist_ok=True)
        os.makedirs('/opt/scale-reader', exist_ok=True)

        # Install required packages using systemd
        service_configs = {
            'scale-reader.service': '''[Unit]
Description=Scale Reader Service
After=network.target

[Service]
Type=simple
ExecStart=/opt/scale-reader/venv/bin/python3 /usr/local/bin/scale_reader.py
Restart=always
User=root
WorkingDirectory=/usr/local/bin

[Install]
WantedBy=multi-user.target''',

            'cloud-control.service': '''[Unit]
Description=Cloud Control Service
After=network.target
Wants=scale-reader.service

[Service]
Type=simple
ExecStart=/opt/scale-reader/venv/bin/python3 /opt/scale-reader/cloud_control.py
Restart=always
User=root
WorkingDirectory=/opt/scale-reader

[Install]
WantedBy=multi-user.target'''
        }

        # Write service files
        for service_name, config in service_configs.items():
            service_path = f'/etc/systemd/system/{service_name}'
            with open(service_path, 'w') as f:
                f.write(config)
            os.chmod(service_path, 0o644)

        # Reload systemd and start services
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        
        for service in ['scale-reader.service', 'cloud-control.service']:
            subprocess.run(['systemctl', 'enable', service], check=True)
            subprocess.run(['systemctl', 'restart', service], check=True)

        return jsonify({
            'success': True,
            'message': 'Services installed and started successfully'
        })

    except subprocess.CalledProcessError as e:
        return jsonify({
            'success': False,
            'message': f'Error installing services: {e.output.decode() if e.output else str(e)}'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error installing services: {str(e)}'
        })

if __name__ == '__main__':
    # Ensure log directory exists
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    logging.info("Starting WiFi Manager service")
    
    # Run the server
    app.run(host='0.0.0.0', port=80, debug=True)