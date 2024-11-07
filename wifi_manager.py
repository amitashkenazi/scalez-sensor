#!/usr/bin/env python3

from flask import Flask, jsonify, render_template_string, request
import subprocess
import logging
import os
import json
import time
from typing import List, Dict, Tuple

# Constants
LOG_PATH = '/var/log/scale-reader/web.log'
WPA_SUPPLICANT_PATH = '/etc/wpa_supplicant/wpa_supplicant.conf'
CONFIG_PATH = '/etc/scale-reader/config.json'

# Configure logging
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

app = Flask(__name__)

# HTML template for the web interface
TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Scale WiFi Setup</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        .card {
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .status {
            font-size: 18px;
            margin: 20px 0;
            padding: 15px;
            border-radius: 4px;
        }
        .status.connected {
            background: #d4edda;
            color: #155724;
        }
        .status.disconnected {
            background: #f8d7da;
            color: #721c24;
        }
        .network-list {
            list-style: none;
            padding: 0;
        }
        .network-item {
            padding: 10px;
            margin: 5px 0;
            background: #f8f9fa;
            border-radius: 4px;
            cursor: pointer;
        }
        .network-item:hover {
            background: #e9ecef;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 5px;
        }
        input[type="text"],
        input[type="password"] {
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            box-sizing: border-box;
        }
        button {
            background: #007bff;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            margin-right: 10px;
        }
        button:hover {
            background: #0056b3;
        }
        button.danger {
            background: #dc3545;
        }
        button.danger:hover {
            background: #c82333;
        }
        .signal-strength {
            float: right;
            color: #6c757d;
        }
        #refresh-button {
            margin-bottom: 20px;
        }
        #loading {
            display: none;
            text-align: center;
            margin: 20px 0;
        }
        .config-info {
            background: #e9ecef;
            padding: 15px;
            border-radius: 4px;
            margin: 20px 0;
        }
        .config-info h3 {
            margin-top: 0;
        }
        .config-item {
            margin: 10px 0;
        }
        .config-label {
            font-weight: bold;
            margin-right: 10px;
        }
    </style>
</head>
<body>
    <div class="card">
        <h1>Scale WiFi Setup</h1>
        
        <div class="config-info">
            <h3>Scale Configuration</h3>
            <div id="config-details">Loading configuration...</div>
        </div>
        
        <div id="status" class="status">
            Checking connection status...
        </div>

        <button id="refresh-button" onclick="refreshNetworks()">
            Refresh Networks
        </button>
        
        <button id="disconnect-button" onclick="disconnectWifi()" class="danger">
            Disconnect WiFi
        </button>

        <div id="loading">Scanning networks...</div>
        
        <div id="networks">
            <h2>Available Networks</h2>
            <ul class="network-list" id="network-list">
            </ul>
        </div>

        <div id="connect-form" style="display: none;">
            <h2>Connect to Network</h2>
            <form onsubmit="return connectToNetwork(event)">
                <div class="form-group">
                    <label for="ssid">Network Name:</label>
                    <input type="text" id="ssid" name="ssid" readonly>
                </div>
                <div class="form-group">
                    <label for="password">Password:</label>
                    <input type="password" id="password" name="password" required>
                </div>
                <button type="submit">Connect</button>
                <button type="button" onclick="hideForm()">Cancel</button>
            </form>
        </div>
    </div>

    <script>
        function updateConfig() {
            fetch('/api/config')
                .then(response => response.json())
                .then(data => {
                    const configDiv = document.getElementById('config-details');
                    let configHtml = '';
                    for (const [key, value] of Object.entries(data)) {
                        configHtml += `<div class="config-item"><span class="config-label">${key}:</span>${value}</div>`;
                    }
                    configDiv.innerHTML = configHtml;
                });
        }

        function updateStatus() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    const statusDiv = document.getElementById('status');
                    if (data.connected) {
                        statusDiv.className = 'status connected';
                        statusDiv.innerHTML = `Connected to: ${data.ssid}<br>IP: ${data.ip}`;
                    } else {
                        statusDiv.className = 'status disconnected';
                        statusDiv.innerHTML = 'Not connected to any network';
                    }
                });
        }

        function disconnectWifi() {
            if (!confirm('Are you sure you want to disconnect from WiFi?')) {
                return;
            }
            
            fetch('/api/disconnect')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('Successfully disconnected from WiFi');
                        setTimeout(updateStatus, 2000);
                    } else {
                        alert('Failed to disconnect: ' + data.error);
                    }
                });
        }

        function refreshNetworks() {
            document.getElementById('loading').style.display = 'block';
            document.getElementById('network-list').innerHTML = '';
            
            fetch('/api/scan')
                .then(response => response.json())
                .then(data => {
                    const networkList = document.getElementById('network-list');
                    networkList.innerHTML = '';
                    
                    data.networks.forEach(network => {
                        const li = document.createElement('li');
                        li.className = 'network-item';
                        li.onclick = () => showConnectForm(network.ssid);
                        li.innerHTML = `
                            ${network.ssid}
                            <span class="signal-strength">${network.signal_strength}%</span>
                        `;
                        networkList.appendChild(li);
                    });
                    document.getElementById('loading').style.display = 'none';
                });
        }

        function showConnectForm(ssid) {
            document.getElementById('connect-form').style.display = 'block';
            document.getElementById('ssid').value = ssid;
        }

        function hideForm() {
            document.getElementById('connect-form').style.display = 'none';
        }

        function connectToNetwork(event) {
            event.preventDefault();
            const formData = {
                ssid: document.getElementById('ssid').value,
                password: document.getElementById('password').value
            };

            fetch('/api/connect', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('Connection successful! The device will now connect to the new network.');
                    hideForm();
                    setTimeout(updateStatus, 5000);
                } else {
                    alert('Connection failed: ' + data.error);
                }
            });

            return false;
        }

        // Initial load
        updateStatus();
        updateConfig();
        refreshNetworks();
        
        // Update status every 10 seconds
        setInterval(updateStatus, 10000);
    </script>
</body>
</html>
"""

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


    
@app.route('/')
def index():
    """Serve the main page"""
    return render_template_string(TEMPLATE)

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
    
    success, error = connect_to_network(data['ssid'], data['password'])
    return jsonify({
        'success': success,
        'error': error
    })

@app.route('/api/disconnect')
def disconnect():
    """Disconnect from current network"""
    success, error = disconnect_wifi()

    return jsonify({
            'success': success,
            'error': error
        })


def connect_to_network(ssid: str, password: str) -> Tuple[bool, str]:
    """Connect to a WiFi network while maintaining AP"""
    try:
        logging.info(f"Attempting to connect to network: {ssid}")
        
        # First disconnect from any existing client connection
        # but preserve the AP interface
        result = subprocess.run(
            ['sudo', '/bin/bash', '/usr/local/bin/wifi-disconnect.sh', '-i', 'wlan0'],
            capture_output=True,
            text=True
        )
        time.sleep(2)
        
        # Connect using the script on wlan0 interface
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
    """Disconnect from WiFi network while maintaining AP"""
    try:
        # Only disconnect wlan0, leaving uap0 (AP interface) untouched
        result = subprocess.run(
            ['sudo', '/bin/bash', '/usr/local/bin/wifi-disconnect.sh', '-i', 'wlan0'],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            return True, ""
        return False, result.stderr
    except Exception as e:
        logging.error(f"Error disconnecting WiFi: {e}")
        return False, str(e)

def get_wifi_status() -> Tuple[bool, str, str]:
    """Get current WiFi connection status (client connection only)"""
    try:
        # Get connection info specifically for wlan0 interface
        result = subprocess.run(
            ['iwgetid', 'wlan0', '-r'], 
            capture_output=True, 
            text=True
        )
        
        if result.returncode == 0 and result.stdout.strip():
            ssid = result.stdout.strip()
            # Get IP address for wlan0
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
            
            logging.info(f"Current connection - SSID: {ssid}, IP: {ip_address}")
            return True, ssid, ip_address
            
        logging.info("No current WiFi connection detected")
        return False, "", ""
    except Exception as e:
        logging.error(f"Error getting WiFi status: {e}")
        return False, "", ""

if __name__ == '__main__':
    # Ensure the log directory exists
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    
    # Run the server on all interfaces
    app.run(host='0.0.0.0', port=80)


  