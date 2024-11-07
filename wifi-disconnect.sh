#!/bin/bash

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root"
    exit 1
fi

# Function to show usage
usage() {
    echo "Usage: $0 -i <interface>"
    echo "Example: $0 -i wlan0"
    exit 1
}

# Parse command line arguments
while getopts "i:" opt; do
    case $opt in
        i) INTERFACE="$OPTARG" ;;
        *) usage ;;
    esac
done

# Check if interface is provided
if [ -z "$INTERFACE" ]; then
    usage
fi

# Check if interface exists
if ! ip link show "$INTERFACE" >/dev/null 2>&1; then
    echo "Interface $INTERFACE does not exist"
    exit 1
fi

echo "Disconnecting WiFi and cleaning up..."
echo "Interface: $INTERFACE"

# Release DHCP lease
echo "Releasing DHCP lease..."
dhclient -r "$INTERFACE" 2>/dev/null

# Kill any running wpa_supplicant processes
echo "Stopping wpa_supplicant..."
killall wpa_supplicant 2>/dev/null

# Remove wpa_supplicant control files
echo "Removing wpa_supplicant control files..."
rm -f /run/wpa_supplicant/* 2>/dev/null

# Bring interface down
echo "Bringing interface down..."
ip link set "$INTERFACE" down

# Remove the configuration file if it exists
CONFIG_FILE="/etc/wpa_supplicant/wpa_supplicant-$INTERFACE.conf"
if [ -f "$CONFIG_FILE" ]; then
    echo "Removing configuration file..."
    rm -f "$CONFIG_FILE"
fi

# Verify disconnection
if ! iw "$INTERFACE" link 2>&1 | grep -q "Not connected"; then
    echo "Warning: Interface might still be connected"
    exit 1
else
    echo "Successfully disconnected from WiFi"
    echo "Interface status:"
    ip link show "$INTERFACE"
fi