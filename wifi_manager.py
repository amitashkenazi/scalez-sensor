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
        }
        button:hover {
            background: #0056b3;
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
    </style>
</head>
<body>
    <div class="card">
        <h1>Scale WiFi Setup</h1>
        
        <div id="status" class="status">
            Checking connection status...
        </div>

        <button id="refresh-button" onclick="refreshNetworks()">
            Refresh Networks
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
                    setTimeout(updateStatus, 5000);  // Update status after 5 seconds
                } else {
                    alert('Connection failed: ' + data.error);
                }
            });

            return false;
        }

        // Initial load
        updateStatus();
        refreshNetworks();
        
        // Update status every 10 seconds
        setInterval(updateStatus, 10000);
    </script>
</body>
</html>
"""

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

def connect_to_network(ssid: str, password: str) -> Tuple[bool, str]:
    """Connect to a WiFi network"""
    try:
        logging.info(f"Attempting to connect to network: {ssid}")
        
        # Normalize the SSID - convert special characters to their ASCII representation
        normalized_ssid = ssid.encode('ascii', 'replace').decode('ascii')
        logging.info(f"Normalized SSID: {normalized_ssid}")
        
        # Create wpa_supplicant configuration with a single network
        wpa_config = f"""
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US

network={{
    ssid="{ssid}"
    psk="{password}"
    key_mgmt=WPA-PSK
    priority=1
    scan_ssid=1
}}
"""
        # Write configuration
        logging.info("Writing new wpa_supplicant configuration")
        with open(WPA_SUPPLICANT_PATH, 'w') as f:
            f.write(wpa_config)
        
        # Set proper permissions
        os.chmod(WPA_SUPPLICANT_PATH, 0o600)
        logging.info("Updated wpa_supplicant permissions")
        
        # Force wpa_supplicant to reload configuration
        logging.info("Reconfiguring wpa_supplicant...")
        try:
            # Try to reconfigure first
            subprocess.run(['wpa_cli', '-i', 'wlan0', 'reconfigure'], check=True)
            logging.info("wpa_supplicant reconfigured")
        except subprocess.CalledProcessError:
            # If reconfigure fails, restart the service
            logging.info("Reconfigure failed, restarting wpa_supplicant service...")
            subprocess.run(['systemctl', 'restart', 'wpa_supplicant'], check=True)
            logging.info("Restarted wpa_supplicant service")
        
        # Reset interface
        logging.info("Resetting wireless interface...")
        subprocess.run(['ip', 'link', 'set', 'wlan0', 'down'], check=True)
        time.sleep(2)
        subprocess.run(['ip', 'link', 'set', 'wlan0', 'up'], check=True)
        
        # Wait for connection
        logging.info("Waiting for connection to establish...")
        max_attempts = 3
        for attempt in range(max_attempts):
            time.sleep(5)
            connected, current_ssid, ip = get_wifi_status()
            logging.info(f"Connection check {attempt + 1}/{max_attempts}: "
                        f"Connected={connected}, SSID={current_ssid}, IP={ip}")
            
            if connected:
                if current_ssid == ssid:
                    logging.info(f"Successfully connected to {ssid} with IP {ip}")
                    return True, ""
                else:
                    logging.warning(f"Connected to different network: {current_ssid}")
            
            if attempt < max_attempts - 1:
                logging.info("Retrying connection...")
                subprocess.run(['wpa_cli', '-i', 'wlan0', 'reconnect'], check=True)
        
        error_msg = f"Failed to connect to {ssid} after {max_attempts} attempts"
        logging.error(error_msg)
        return False, error_msg
        
    except subprocess.CalledProcessError as e:
        error_msg = f"Command failed: {e.cmd}. Return code: {e.returncode}"
        logging.error(error_msg)
        return False, error_msg
    except Exception as e:
        logging.error(f"Error connecting to network: {str(e)}")
        return False, str(e)

def get_wifi_status() -> Tuple[bool, str, str]:
    """Get current WiFi connection status with improved SSID handling"""
    try:
        # Get connection info
        result = subprocess.run(['iwgetid', '-r'], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            ssid = result.stdout.strip()
            # Get IP address
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
            
            # Additional debug logging
            logging.info(f"Current connection - SSID: {ssid}, IP: {ip_address}")
            return True, ssid, ip_address
            
        logging.info("No current WiFi connection detected")
        return False, "", ""
    except Exception as e:
        logging.error(f"Error getting WiFi status: {e}")
        return False, "", ""
    
@app.route('/')
def index():
    """Serve the main page"""
    return render_template_string(TEMPLATE)

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

if __name__ == '__main__':
    # Ensure the log directory exists
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    
    # Run the server on all interfaces
    app.run(host='0.0.0.0', port=80)