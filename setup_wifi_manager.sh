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
mkdir -p /var/log/scale-reader

# Install required packages
print_status "Installing required packages..."
apt-get update
apt-get install -y python3-flask python3-wifi python3-pip

# Install additional Python packages
print_status "Installing Python packages..."
pip3 install flask requests

# Copy WiFi manager script
print_status "Installing WiFi manager script..."
cp wifi_manager.py /usr/local/bin/
chmod +x /usr/local/bin/wifi_manager.py

# Create systemd service
print_status "Creating systemd service..."
cat > /etc/systemd/system/wifi-manager.service << EOL
[Unit]
Description=WiFi Manager Web Interface
After=network.target

[Service]
ExecStart=/usr/local/bin/wifi_manager.py
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
chown root:root /usr/local/bin/wifi_manager.py
chmod 755 /var/log/scale-reader
touch /var/log/scale-reader/web.log
chmod 644 /var/log/scale-reader/web.log
chown root:root /var/log/scale-reader/web.log

# Create a directory for wpa_supplicant if it doesn't exist
mkdir -p /etc/wpa_supplicant

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

# Enable and start the service
print_status "Enabling and starting service..."
systemctl daemon-reload
systemctl enable wifi-manager.service
systemctl start wifi-manager.service

# Verify service status
if systemctl is-active --quiet wifi-manager; then
    print_success "WiFi manager service is running"
else
    print_error "WiFi manager service failed to start"
    echo "Check the service status with: systemctl status wifi-manager"
fi

# Final instructions
echo
echo -e "${GREEN}WiFi Manager setup completed!${NC}"
echo
echo "The web interface should now be accessible at:"
echo "  http://192.168.4.1"
echo
echo "You can monitor the service using:"
echo "  systemctl status wifi-manager"
echo
echo "To view logs:"
echo "  journalctl -u wifi-manager -f"
echo "  tail -f /var/log/scale-reader/web.log"
echo
echo "If the service doesn't start properly, try:"
echo "  sudo systemctl restart wifi-manager"
echo
echo "To test the web interface:"
echo "1. Connect to the Raspberry Pi's AP network"
echo "2. Open a web browser and navigate to http://192.168.4.1"
echo "3. You should see the WiFi setup interface"