#!/bin/bash

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root"
    exit 1
fi

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
    echo "Interface $INTERFACE does not exist"
    exit 1
fi

echo "Setting up WiFi connection..."
echo "Interface: $INTERFACE"
echo "SSID: $SSID"

# Clean up existing connections
echo "Cleaning up existing connections..."
killall wpa_supplicant 2>/dev/null
rm -f /run/wpa_supplicant/* 2>/dev/null
ip link set "$INTERFACE" down

# Create wpa_supplicant configuration
echo "Generating wpa_supplicant configuration..."
CONFIG_FILE="/etc/wpa_supplicant/wpa_supplicant-$INTERFACE.conf"

# Generate configuration with wpa_passphrase
wpa_passphrase "$SSID" "$PASSWORD" > "$CONFIG_FILE"

# Add control interface configuration
sed -i '1i ctrl_interface=/run/wpa_supplicant\nupdate_config=1\n' "$CONFIG_FILE"

# Set proper permissions
chmod 600 "$CONFIG_FILE"

# Bring interface up
ip link set "$INTERFACE" up

# Start wpa_supplicant
echo "Starting wpa_supplicant..."
wpa_supplicant -B -i "$INTERFACE" -c "$CONFIG_FILE"

if [ $? -ne 0 ]; then
    echo "Failed to start wpa_supplicant"
    exit 1
fi

# Get IP address
echo "Requesting IP address..."
dhclient -v "$INTERFACE"

# Verify connection
echo "Verifying connection..."
sleep 2

if iw "$INTERFACE" link | grep -q "Connected to"; then
    echo "Successfully connected to $SSID"
    echo "Connection details:"
    iw "$INTERFACE" link
    ip addr show "$INTERFACE" | grep "inet "
    echo "Testing internet connectivity..."
    if ping -c 1 8.8.8.8 >/dev/null 2>&1; then
        echo "Internet connection successful!"
    else
        echo "Warning: Connected to WiFi but no internet access"
    fi
else
    echo "Failed to connect to $SSID"
    exit 1
fi