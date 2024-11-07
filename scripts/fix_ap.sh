#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${YELLOW}>>> $1${NC}"
}

# Stop services
print_status "Stopping services..."
systemctl stop hostapd
systemctl stop dnsmasq

# Remove existing uap0 interface if it exists
print_status "Cleaning up existing interface..."
iw dev uap0 del 2>/dev/null || true

# Create and configure the AP interface
print_status "Setting up AP interface..."
iw dev wlan0 interface add uap0 type __ap
ip addr add 192.168.4.1/24 dev uap0
ip link set uap0 up

# Configure dnsmasq
print_status "Configuring DNSMASQ..."
cat > /etc/dnsmasq.conf << EOL
interface=uap0
dhcp-range=192.168.4.50,192.168.4.150,255.255.255.0,24h
dhcp-option=option:router,192.168.4.1
dhcp-option=option:dns-server,8.8.8.8,8.8.4.4
EOL

# Set up NAT
print_status "Configuring NAT..."
# Clear existing rules
iptables -t nat -F
iptables -F FORWARD

# Set up NAT rules
iptables -t nat -A POSTROUTING -o wlan0 -j MASQUERADE
iptables -A FORWARD -i wlan0 -o uap0 -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i uap0 -o wlan0 -j ACCEPT

# Make IP forwarding permanent
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/90-ip-forward.conf
sysctl -p /etc/sysctl.d/90-ip-forward.conf

# Start services
print_status "Starting services..."
systemctl start hostapd
sleep 2
systemctl start dnsmasq

# Create startup script to ensure interface is created on boot
print_status "Creating startup script..."
cat > /usr/local/bin/setup_ap_interface.sh << EOL
#!/bin/bash
# Remove interface if it exists
iw dev uap0 del 2>/dev/null || true

# Create AP interface
iw dev wlan0 interface add uap0 type __ap
ip addr add 192.168.4.1/24 dev uap0
ip link set uap0 up

# Set up NAT
iptables -t nat -A POSTROUTING -o wlan0 -j MASQUERADE
iptables -A FORWARD -i wlan0 -o uap0 -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i uap0 -o wlan0 -j ACCEPT
EOL

chmod +x /usr/local/bin/setup_ap_interface.sh

# Create systemd service for interface setup
cat > /etc/systemd/system/setup-ap-interface.service << EOL
[Unit]
Description=Setup AP Interface
Before=hostapd.service
After=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/setup_ap_interface.sh

[Install]
WantedBy=multi-user.target
EOL

# Enable the service
systemctl daemon-reload
systemctl enable setup-ap-interface.service

print_status "Configuration complete. Verifying setup..."

# Show interface status
ip addr show uap0

echo
print_status "To verify everything is working:"
echo "1. Check interface status:"
echo "   ip addr show uap0"
echo
echo "2. Check hostapd status:"
echo "   systemctl status hostapd"
echo
echo "3. Check dnsmasq status:"
echo "   systemctl status dnsmasq"
echo
echo "4. To monitor DHCP requests:"
echo "   journalctl -f -u dnsmasq"