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

# Check if adminPage directory exists
if [ ! -d "./adminPage" ]; then
    print_error "adminPage directory not found in current directory"
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
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3-flask \
    python3-pip \
    wireless-tools \
    wpasupplicant \
    python3-werkzeug \
    python3-venv \
    python3-full \
    net-tools \
    iw \
    sudo \
    curl

# Create and configure virtual environment
print_status "Setting up Python virtual environment..."
python3 -m venv /opt/scale-reader/venv

# Install Python packages in virtual environment
print_status "Installing Python packages in virtual environment..."
/opt/scale-reader/venv/bin/pip install --upgrade pip
/opt/scale-reader/venv/bin/pip install \
    flask \
    requests \
    werkzeug \
    awsiotsdk \
    psutil

# Copy adminPage files
print_status "Copying adminPage files..."
cp -r ./adminPage/static/* /usr/local/bin/static/
cp -r ./adminPage/templates/* /usr/local/bin/templates/
cp ./adminPage/wifi_manager.py /usr/local/bin/
cp ./adminPage/installationManager.jsx /usr/local/bin/static/components/
cp ./rpi_setup_wo_wifi.sh /usr/local/bin/

# Copy WiFi utility scripts
print_status "Installing WiFi utility scripts..."
cp connect_to_wifi.sh /usr/local/bin/
cp wifi-disconnect.sh /usr/local/bin/
chmod +x /usr/local/bin/connect_to_wifi.sh
chmod +x /usr/local/bin/wifi-disconnect.sh
chmod +x /usr/local/bin/wifi_manager.py
chmod +x /usr/local/bin/rpi_setup_wo_wifi.sh

# Create systemd service
print_status "Creating systemd service..."
cat > /etc/systemd/system/wifi-manager.service << EOL
[Unit]
Description=WiFi Manager Web Interface
After=network.target hostapd.service
Wants=network.target

[Service]
ExecStart=/opt/scale-reader/venv/bin/python3 /usr/local/bin/wifi_manager.py
Restart=always
RestartSec=5
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
chmod 644 /usr/local/bin/static/*
chmod 644 /usr/local/bin/templates/*
chmod 755 /var/log/scale-reader
touch /var/log/scale-reader/web.log
chmod 644 /var/log/scale-reader/web.log
chown root:root /var/log/scale-reader/web.log

# Set virtual environment permissions
chown -R root:root /opt/scale-reader
chmod -R 755 /opt/scale-reader

# Create directories for certificates and configurations
print_status "Setting up certificate directories..."
mkdir -p /etc/scale-reader/certs
chmod 755 /etc/scale-reader/certs

# Create initial wpa_supplicant.conf if it doesn't exist
if [ ! -f /etc/wpa_supplicant/wpa_supplicant.conf ]; then
    print_status "Creating initial wpa_supplicant.conf..."
    cat > /etc/wpa_supplicant/wpa_supplicant.conf << EOL
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US
EOL
    chmod 600 /etc/wpa_supplicant/wpa_supplicant.conf
fi

# Enable and start the service
print_status "Enabling and starting service..."
systemctl daemon-reload
systemctl enable wifi-manager.service
systemctl restart wifi-manager.service

# Verify service status
if systemctl is-active --quiet wifi-manager; then
    print_success "WiFi manager service is running"
    
    # Get IP addresses for user reference
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
    journalctl -u wifi-manager -n 50
    exit 1
fi

# Create helper scripts
print_status "Creating helper scripts..."

# Create WiFi test script
cat > /usr/local/bin/test-wifi << 'EOL'
#!/bin/bash
echo "Testing WiFi connectivity..."
echo "Current network status:"
iwconfig wlan0
echo
echo "IP configuration:"
ip addr show wlan0
echo
echo "Testing internet connectivity..."
ping -c 3 8.8.8.8
echo
echo "DNS resolution test:"
nslookup google.com
EOL
chmod +x /usr/local/bin/test-wifi

# Create service restart script
cat > /usr/local/bin/restart-wifi-manager << 'EOL'
#!/bin/bash
echo "Restarting WiFi Manager service..."
sudo systemctl restart wifi-manager
echo "Service status:"
sudo systemctl status wifi-manager
EOL
chmod +x /usr/local/bin/restart-wifi-manager

# Create log viewer script
cat > /usr/local/bin/view-wifi-logs << 'EOL'
#!/bin/bash
echo "=== WiFi Manager Logs ==="
echo "Press Ctrl+C to exit"
echo
sudo journalctl -u wifi-manager -f
EOL
chmod +x /usr/local/bin/view-wifi-logs

print_success "Setup completed successfully!"
echo
echo "Directory Structure:"
echo "   - Web Interface: /usr/local/bin/{static,templates}"
echo "   - Certificates: /etc/scale-reader/certs"
echo "   - WiFi Config: /etc/scale-reader/wifi"
echo "   - Logs: /var/log/scale-reader"
echo "   - Virtual Environment: /opt/scale-reader/venv"
echo
echo "Service Management:"
echo "   To restart: sudo systemctl restart wifi-manager"
echo "   To stop: sudo systemctl stop wifi-manager"
echo "   To start: sudo systemctl start wifi-manager"
echo "   To check status: sudo systemctl status wifi-manager"
echo
echo "Helper Scripts:"
echo "   - test-wifi: Test WiFi connectivity"
echo "   - restart-wifi-manager: Restart the service"
echo "   - view-wifi-logs: View service logs"
echo
echo "Troubleshooting:"
echo "   If the service fails to start, check:"
echo "   - System logs: journalctl -u wifi-manager"
echo "   - Application logs: /var/log/scale-reader/web.log"