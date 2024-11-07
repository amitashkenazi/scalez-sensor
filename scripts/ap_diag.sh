#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo_status() {
    echo -e "${YELLOW}>>> $1${NC}"
}

echo_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

echo_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Check hostapd configuration
echo_status "Checking hostapd configuration..."
if ! grep -q "^interface=uap0" /etc/hostapd/hostapd.conf; then
    echo_error "Wrong interface in hostapd.conf"
    exit 1
fi

# Check if interface exists
echo_status "Checking uap0 interface..."
if ! ip link show uap0 >/dev/null 2>&1; then
    echo_error "uap0 interface not found"
    exit 1
fi

# Check IP assignment
echo_status "Checking IP configuration..."
if ! ip addr show uap0 | grep -q "192.168.4.1/24"; then
    echo_error "IP address not properly configured on uap0"
    exit 1
fi

# Check hostapd status
echo_status "Checking hostapd service..."
if ! systemctl is-active --quiet hostapd; then
    echo_error "hostapd service is not running"
    systemctl status hostapd
    exit 1
fi

# Check dnsmasq status
echo_status "Checking dnsmasq service..."
if ! systemctl is-active --quiet dnsmasq; then
    echo_error "dnsmasq service is not running"
    systemctl status dnsmasq
    exit 1
fi

# Check IP forwarding
echo_status "Checking IP forwarding..."
if [ "$(cat /proc/sys/net/ipv4/ip_forward)" != "1" ]; then
    echo_error "IP forwarding is not enabled"
    exit 1
fi

# Check NAT rules
echo_status "Checking NAT rules..."
if ! iptables -t nat -L | grep -q "MASQUERADE"; then
    echo_error "NAT rules not properly configured"
    exit 1
fi

# Check hostapd debug output
echo_status "Checking hostapd debug output..."
hostapd_pid=$(pgrep hostapd)
if [ -n "$hostapd_pid" ]; then
    echo "hostapd process found (PID: $hostapd_pid)"
    # Kill and restart in debug mode temporarily
    systemctl stop hostapd
    timeout 10 hostapd -dd /etc/hostapd/hostapd.conf > /tmp/hostapd_debug.log 2>&1 &
    sleep 5
    systemctl start hostapd
    echo "Debug log written to /tmp/hostapd_debug.log"
else
    echo_error "hostapd process not found"
fi

echo_success "Diagnostic complete. Check the output above for any errors."