#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${YELLOW}>>> $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Stop dnsmasq
print_status "Stopping dnsmasq service..."
systemctl stop dnsmasq

# Check if another process is using port 53
print_status "Checking if port 53 is in use..."
if netstat -tuln | grep -q ":53 "; then
    print_error "Port 53 is already in use. Finding process..."
    lsof -i :53
    print_status "Attempting to stop conflicting service..."
    systemctl stop systemd-resolved
    systemctl disable systemd-resolved
fi

# Backup existing config
print_status "Backing up existing configuration..."
if [ -f /etc/dnsmasq.conf ]; then
    cp /etc/dnsmasq.conf /etc/dnsmasq.conf.backup
fi

# Create clean configuration
print_status "Creating new configuration..."
cat > /etc/dnsmasq.conf << EOL
# Bind to AP interface only
interface=uap0
# Don't bind to wildcard address (prevent port conflicts)
bind-interfaces
# DHCP range
dhcp-range=192.168.4.50,192.168.4.150,255.255.255.0,24h
# Router and DNS options
dhcp-option=option:router,192.168.4.1
dhcp-option=option:dns-server,8.8.8.8,8.8.4.4
# Log queries
log-queries
# Log DHCP
log-dhcp
EOL

# Set correct permissions
print_status "Setting correct permissions..."
chmod 644 /etc/dnsmasq.conf
chown root:root /etc/dnsmasq.conf

# Ensure the interface exists and has correct IP
print_status "Checking uap0 interface..."
if ! ip addr show uap0 2>/dev/null | grep -q "192.168.4.1/24"; then
    print_status "Configuring uap0 interface..."
    ip addr flush dev uap0 2>/dev/null || true
    ip addr add 192.168.4.1/24 dev uap0 || true
    ip link set uap0 up || true
fi

# Start dnsmasq in debug mode temporarily
print_status "Testing dnsmasq in debug mode..."
dnsmasq --test

# If test passes, start the service
if [ $? -eq 0 ]; then
    print_status "Starting dnsmasq service..."
    systemctl restart dnsmasq
    sleep 2
    
    if systemctl is-active --quiet dnsmasq; then
        print_success "DNSMasq is now running successfully!"
        print_status "You can check the logs with: journalctl -u dnsmasq -f"
    else
        print_error "DNSMasq failed to start. Checking logs..."
        journalctl -u dnsmasq -n 50
    fi
else
    print_error "DNSMasq configuration test failed"
fi
