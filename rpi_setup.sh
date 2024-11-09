#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

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

# Function to check if script is run as root
check_root() {
    if [ "$EUID" -ne 0 ]; then 
        print_error "Please run as root (use sudo)"
        exit 1
    fi
}

# Function to handle errors
handle_error() {
    print_error "$1"
    exit 1
}

# Function to verify certificates
verify_certificates() {
    print_status "Verifying certificates..."
    
    local CERT_DIR="/etc/scale-reader/certs"
    local REQUIRED_FILES=("device.cert.pem" "device.private.key" "root-CA.crt")
    
    # Check each required file
    for file in "${REQUIRED_FILES[@]}"; do
        if [ ! -f "$CERT_DIR/$file" ]; then
            print_error "Missing certificate file: $file"
            echo
            echo "Please copy the following files to /tmp/ first:"
            echo "  - device.cert.pem"
            echo "  - device.private.key"
            echo "  - root-CA.crt"
            echo
            echo "You can copy them from your Mac using:"
            echo "  scp ./certs/* pi@<raspberry-pi-ip>:/tmp/"
            echo
            exit 1
        fi
    done
    
    # Set proper permissions
    chmod 600 "$CERT_DIR"/*
    chown root:root "$CERT_DIR"/*
    
    print_success "Certificates verified successfully"
}

# Function to move certificates from /tmp
move_certificates() {
    print_status "Moving certificates from /tmp..."
    
    # Create certificates directory
    mkdir -p /etc/scale-reader/certs
    
    # Check if certificate files exist in /tmp
    if ! ls /tmp/*.{pem,key,crt} >/dev/null 2>&1; then
        print_error "No certificate files found in /tmp"
        echo "Please copy the following files to /tmp first:"
        echo "  - device.cert.pem"
        echo "  - device.private.key"
        echo "  - root-CA.crt"
        echo
        echo "You can copy them from your Mac using:"
        echo "  scp ./certs/* pi@<raspberry-pi-ip>:/tmp/"
        exit 1
    fi
    
    # Move certificates
    mv /tmp/*.{pem,key,crt} /etc/scale-reader/certs/ 2>/dev/null || true
    
    # Set proper permissions
    chmod 600 /etc/scale-reader/certs/*
    chown root:root /etc/scale-reader/certs/*
    
    print_success "Certificates moved successfully"
}

# Function to prompt for configuration values
get_config_values() {
    print_status "Enter configuration values:"
    
    # Get Scale ID
    read -p "Enter Scale ID: " SCALE_ID
    if [ -z "$SCALE_ID" ]; then
        handle_error "Scale ID cannot be empty"
    fi
    
    # Get Serial Port
    read -p "Enter Serial Port [/dev/ttyUSB0]: " SERIAL_PORT
    SERIAL_PORT=${SERIAL_PORT:-/dev/ttyUSB0}
    
    # Get Baud Rate
    read -p "Enter Baud Rate [1200]: " BAUD_RATE
    BAUD_RATE=${BAUD_RATE:-1200}
    
    # Get WiFi credentials for client connection
    read -p "Enter WiFi SSID to connect to: " WIFI_SSID
    read -s -p "Enter WiFi Password: " WIFI_PASSWORD
    echo
    
    # Get AWS IoT endpoint
    read -p "Enter AWS IoT endpoint (e.g., xxxxxx-ats.iot.us-east-1.amazonaws.com): " IOT_ENDPOINT
    if [ -z "$IOT_ENDPOINT" ]; then
        handle_error "IoT endpoint cannot be empty"
    fi
}

# Function to copy required files
copy_required_files() {
    print_status "Copying required files..."
    
    # Create necessary directories
    mkdir -p /usr/local/bin
    mkdir -p /var/log/scale-reader
    mkdir -p /opt/scale-reader
    
    # Copy scripts
    cp network_ap_setup.sh /usr/local/bin/
    cp connect_to_wifi.sh /usr/local/bin/
    cp wifi-disconnect.sh /usr/local/bin/
    cp setup_wifi_connection.sh /usr/local/bin/
    cp scale_reader.py /usr/local/bin/
    cp cloud_control.py /opt/scale-reader/
    cp wifi_manager.py /usr/local/bin/
    
    chmod +x /usr/local/bin/*.sh
    chmod +x /usr/local/bin/*.py
    chmod +x /opt/scale-reader/cloud_control.py
}

# Main setup procedure
main() {
    print_status "Starting Raspberry Pi Setup"
    
    # Check if running as root
    check_root
    
    # Move certificates from /tmp
    move_certificates
    
    # Verify certificates
    verify_certificates
    
    # Get configuration values
    get_config_values
    
    # Copy required files
    copy_required_files
    
    # Set up access point
    bash /usr/local/bin/network_ap_setup.sh
    
    # Set up WiFi client
    bash /usr/local/bin/connect_to_wifi.sh -i wlan0 -s "$WIFI_SSID" -p "$WIFI_PASSWORD"
    bash /usr/local/bin/setup_wifi_connection.sh
    
    # Create IoT configuration
    print_status "Creating IoT configuration..."
    cat > /etc/scale-reader/config.json << EOL
{
    "scale_id": "$SCALE_ID",
    "serial_port": "$SERIAL_PORT",
    "baud_rate": $BAUD_RATE,
    "iot_endpoint": "$IOT_ENDPOINT"
}
EOL
    chmod 600 /etc/scale-reader/config.json
    
    # Set up Python virtual environment
    print_status "Setting up Python virtual environment..."
    apt-get update
    apt-get install -y python3-venv python3-pip
    python3 -m venv /opt/scale-reader/venv
    
    # Install required Python packages
    /opt/scale-reader/venv/bin/pip install \
        awsiotsdk \
        pyserial \
        boto3 \
        flask \
        requests \
        psutil
    
    # Create systemd services
    print_status "Creating systemd services..."
    
    # Scale reader service
    cat > /etc/systemd/system/scale-reader.service << EOL
[Unit]
Description=Scale Reader Service
After=network.target

[Service]
Type=simple
ExecStart=/opt/scale-reader/venv/bin/python3 /usr/local/bin/scale_reader.py
Restart=always
RestartSec=10
User=root
Environment=PYTHONUNBUFFERED=1
WorkingDirectory=/usr/local/bin

[Install]
WantedBy=multi-user.target
EOL

    # Cloud control service
    cat > /etc/systemd/system/cloud-control.service << EOL
[Unit]
Description=Cloud Control Service
After=network.target
Wants=scale-reader.service

[Service]
Type=simple
ExecStart=/opt/scale-reader/venv/bin/python3 /opt/scale-reader/cloud_control.py
Restart=always
RestartSec=10
User=root
Environment=PYTHONUNBUFFERED=1
WorkingDirectory=/opt/scale-reader

[Install]
WantedBy=multi-user.target
EOL

    # Enable and start services
    systemctl daemon-reload
    systemctl enable scale-reader.service cloud-control.service
    systemctl start scale-reader.service cloud-control.service
    
    print_success "Setup completed successfully!"
    echo
    echo "Access Point Details:"
    echo "  SSID: ScaleSetup"
    echo "  Password: scale12345"
    echo "  IP Address: 192.168.4.1"
    echo
    echo "Connected to WiFi network: $WIFI_SSID"
    echo
    echo "Services status:"
    systemctl status hostapd --no-pager
    systemctl status dnsmasq --no-pager
    systemctl status scale-reader --no-pager
    systemctl status cloud-control --no-pager
    echo
    echo "You can monitor the logs with:"
    echo "  Scale reader: journalctl -u scale-reader -f"
    echo "  Cloud control: journalctl -u cloud-control -f"
    echo "  Access point: journalctl -u hostapd -f"
    echo "  DHCP: journalctl -u dnsmasq -f"
}

# Run main setup
main