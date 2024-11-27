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

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Function to show usage
usage() {
    echo "Usage: $0 -i <interface> -s <ssid> -p <password>"
    echo "Example: $0 -i wlan0 -s MyNetwork -p MyPassword"
    exit 1
}

# Parse command line arguments
while getopts "i:s:p:" opt; do
    case $opt in
        i) INTERFACE="$OPTARG" ;;
        s) SSID="$OPTARG" ;;
        p) PASSWORD="$OPTARG" ;;
        *) usage ;;
    esac
done

# Check if all required parameters are provided
if [ -z "$INTERFACE" ] || [ -z "$SSID" ] || [ -z "$PASSWORD" ]; then
    usage
fi

# Check if interface exists
if ! ip link show "$INTERFACE" >/dev/null 2>&1; then
    print_error "Interface $INTERFACE does not exist"
    exit 1
fi

print_status "Setting up WiFi connection..."
print_status "Interface: $INTERFACE"
print_status "SSID: $SSID"

# Clean up existing connection for specific interface only
print_status "Running cleanup..."
pid=$(pgrep -f "wpa_supplicant.*${INTERFACE}")
if [ ! -z "$pid" ]; then
    kill "$pid" || true
    sleep 2
fi

# Remove control interface for specific interface only
rm -f "/run/wpa_supplicant/${INTERFACE}" || true
sleep 1

# Bring interface down
ip link set "$INTERFACE" down
sleep 1

# Generate wpa_supplicant configuration
print_status "Generating wpa_supplicant configuration..."
CONFIG_FILE="/etc/wpa_supplicant/wpa_supplicant-${INTERFACE}.conf"

# Generate configuration with wpa_passphrase
cat > "$CONFIG_FILE" << EOL
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
country=US
update_config=1

network={
    ssid="$SSID"
    scan_ssid=1
    key_mgmt=WPA-PSK
    psk="$PASSWORD"
    priority=1
}
EOL

chmod 600 "$CONFIG_FILE"

# Bring interface up
ip link set "$INTERFACE" up
sleep 1

# Start wpa_supplicant specifically for this interface
print_status "Starting wpa_supplicant..."
wpa_supplicant -B -i "$INTERFACE" -c "$CONFIG_FILE"

if [ $? -ne 0 ]; then
    print_error "Failed to start wpa_supplicant"
    # Clean up on failure
    rm -f "/run/wpa_supplicant/${INTERFACE}"
    exit 1
fi

# Wait for connection
print_status "Waiting for connection..."
max_attempts=15
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if iw "$INTERFACE" link | grep -q "Connected to"; then
        break
    fi
    echo -n "."
    sleep 1
    attempt=$((attempt + 1))
done
echo

# Get IP address
print_status "Requesting IP address..."
dhclient -v "$INTERFACE"

# Verify connection
if iw "$INTERFACE" link | grep -q "Connected to"; then
    print_success "Successfully connected to $SSID"
    echo "Connection details:"
    iw "$INTERFACE" link
    echo "IP Configuration:"
    ip addr show "$INTERFACE" | grep "inet "
    
    # Test internet connectivity
    if ping -c 1 8.8.8.8 >/dev/null 2>&1; then
        print_success "Internet connection successful"
    else
        echo -e "${YELLOW}Warning: Connected to WiFi but no internet access${NC}"
    fi
else
    print_error "Failed to connect to $SSID"
    # Clean up on failure
    rm -f "/run/wpa_supplicant/${INTERFACE}"
    exit 1
fi