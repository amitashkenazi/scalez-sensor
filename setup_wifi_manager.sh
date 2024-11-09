#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print status messages
print_status() {
    echo -e "${YELLOW}>>> $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "Please run as root (use sudo)"
    exit 1
fi

# Create necessary directories
print_status "Creating directories..."
mkdir -p /usr/local/bin
mkdir -p /usr/local/bin/static
mkdir -p /usr/local/bin/templates
mkdir -p /var/log/scale-reader
mkdir -p /etc/wpa_supplicant
mkdir -p /etc/scale-reader/wifi
mkdir -p /etc/scale-reader/certs
mkdir -p /opt/scale-reader

# Install required packages
print_status "Installing required packages..."
apt-get update
apt-get install -y python3-flask python3-pip wireless-tools wpasupplicant python3-werkzeug python3-venv python3-full

# Create and configure virtual environment
print_status "Setting up Python virtual environment..."
python3 -m venv /opt/scale-reader/venv

# Install Python packages in virtual environment
print_status "Installing Python packages in virtual environment..."
/opt/scale-reader/venv/bin/pip install flask requests werkzeug

# Create React component file
print_status "Creating React component..."
cat > /usr/local/bin/static/scale_setup.jsx << 'EOL'
import React, { useState, useCallback, useEffect } from 'react';

function ScaleSetup() {
  // Component code here (copy the entire React component from above)
}

export default ScaleSetup;

// Mount the component
ReactDOM.render(<ScaleSetup />, document.getElementById('root'));
EOL

# Create HTML template
print_status "Creating HTML template..."
cat > /usr/local/bin/templates/index.html << 'EOL'
<!DOCTYPE html>
<html>
<head>
    <title>Scale Setup</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://unpkg.com/react@17/umd/react.production.min.js"></script>
    <script src="https://unpkg.com/react-dom@17/umd/react-dom.production.min.js"></script>
    <script src="https://unpkg.com/babel-standalone@6/babel.min.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body>
    <div id="root"></div>
    <script type="text/babel" src="{{ url_for('static', filename='scale_setup.jsx') }}"></script>
</body>
</html>
EOL

# Copy WiFi manager script
print_status "Installing WiFi manager script..."
cp wifi_manager.py /usr/local/bin/
chmod +x /usr/local/bin/wifi_manager.py

# Copy WiFi utility scripts
print_status "Installing WiFi utility scripts..."
cp connect_to_wifi.sh /usr/local/bin/
cp wifi-disconnect.sh /usr/local/bin/
chmod +x /usr/local/bin/connect_to_wifi.sh
chmod +x /usr/local/bin/wifi-disconnect.sh

# Create systemd service
print_status "Creating systemd service..."
cat > /etc/systemd/system/wifi-manager.service << EOL
[Unit]
Description=WiFi Manager Web Interface
After=network.target

[Service]
ExecStart=/opt/scale-reader/venv/bin/python3 /usr/local/bin/wifi_manager.py
Restart=always
User=root
Environment=FLASK_ENV=production
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPATH=/usr/local/bin
WorkingDirectory=/usr/local/bin

[Install]
WantedBy=multi-user.target
EOL

# Set proper permissions
print_status "Setting permissions..."
chmod 644 /etc/systemd/system/wifi-manager.service
chown -R root:root /usr/local/bin
chmod -R 755 /usr/local/bin
chmod 644 /usr/local/bin/static/scale_setup.jsx
chmod 644 /usr/local/bin/templates/index.html
chmod 755 /var/log/scale-reader
touch /var/log/scale-reader/web.log
chmod 644 /var/log/scale-reader/web.log
chown root:root /var/log/scale-reader/web.log

# Set virtual environment permissions
chown -R root:root /opt/scale-reader
chmod -R 755 /opt/scale-reader

# Ensure wpa_supplicant.conf exists with proper permissions
if [ ! -f /etc/wpa_supplicant/wpa_supplicant.conf ]; then
    print_status "Creating initial wpa_supplicant.conf..."
    cat > /etc/wpa_supplicant/wpa_supplicant.conf << EOL
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US
EOL
fi
chmod 600 /etc/wpa_supplicant/wpa_supplicant.conf

# Create directory for certificate uploads if it doesn't exist
print_status "Setting up certificate directory..."
mkdir -p /etc/scale-reader/certs
chmod 755 /etc/scale-reader/certs

# Enable and start the service
print_status "Enabling and starting service..."
systemctl daemon-reload
systemctl enable wifi-manager.service
systemctl restart wifi-manager.service

# Verify service status
if systemctl is-active --quiet wifi-manager; then
    print_success "WiFi manager service is running"
    
    # Get IP address for user reference
    IP_ADDRESS=$(ip -4 addr show wlan0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' || echo "Unknown")
    AP_ADDRESS=$(ip -4 addr show uap0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' || echo "192.168.4.1")
    
    echo
    echo "The web interface should now be accessible at:"
    echo "  http://${IP_ADDRESS} (if connected to WiFi)"
    echo "  http://${AP_ADDRESS} (via AP interface)"
    echo
    echo "You can monitor the service using:"
    echo "  systemctl status wifi-manager"
    echo
    echo "To view logs:"
    echo "  journalctl -u wifi-manager -f"
    echo "  tail -f /var/log/scale-reader/web.log"
else
    print_error "WiFi manager service failed to start"
    echo "Check the service status with: systemctl status wifi-manager"
fi

# Final notes
echo
echo "Additional Features:"
echo "1. WiFi Connection Management"
echo "2. Certificate Upload (via drag-and-drop)"
echo "3. Service Installation and Configuration"
echo
echo "Directories:"
echo "- Web Interface: /usr/local/bin/{static,templates}"
echo "- Certificates: /etc/scale-reader/certs"
echo "- WiFi Config: /etc/scale-reader/wifi"
echo "- Logs: /var/log/scale-reader"
echo "- Virtual Environment: /opt/scale-reader/venv"
echo
echo "If you need to restart the service:"
echo "  sudo systemctl restart wifi-manager"