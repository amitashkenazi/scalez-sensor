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

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "Please run as root (use sudo)"
    exit 1
fi

# Install required packages
print_status "Installing required packages..."
apt-get update
apt-get install -y hostapd dnsmasq python3-flask python3-pip

# Stop all wireless services
print_status "Stopping wireless services..."
systemctl stop hostapd
systemctl stop dnsmasq
systemctl stop wpa_supplicant

# Unmask and enable services
systemctl unmask hostapd
systemctl unmask hostapd.service

# Unblock wifi
print_status "Unblocking WiFi..."
rfkill unblock wifi

# Clean up interfaces
print_status "Cleaning up interfaces..."
ip link set wlan0 down
iw dev uap0 del 2>/dev/null || true
sleep 2

# Reset wlan0 to clean state
print_status "Resetting wlan0..."
ip link set wlan0 down
iw wlan0 set type managed
ip link set wlan0 up
sleep 2

# Create new AP interface
print_status "Creating AP interface..."
iw dev wlan0 interface add uap0 type __ap || {
    print_error "Failed to create uap0 interface"
    exit 1
}
sleep 2

# Configure hostapd
print_status "Configuring hostapd..."
cat > /etc/hostapd/hostapd.conf << EOL
interface=uap0
driver=nl80211
ssid=ScaleSetup
hw_mode=g
channel=6
auth_algs=1
wpa=2
wpa_passphrase=scale12345
wpa_key_mgmt=WPA-PSK
wpa_pairwise=CCMP
rsn_pairwise=CCMP
country_code=US
ieee80211d=1
wmm_enabled=1
EOL

chmod 600 /etc/hostapd/hostapd.conf

# Point default config to our config
echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' > /etc/default/hostapd

# Configure dnsmasq
print_status "Configuring dnsmasq..."
# Backup original config if it exists
if [ -f /etc/dnsmasq.conf ]; then
    cp /etc/dnsmasq.conf /etc/dnsmasq.conf.orig
fi

cat > /etc/dnsmasq.conf << EOL
interface=uap0
dhcp-range=192.168.4.50,192.168.4.150,255.255.255.0,24h
dhcp-option=option:router,192.168.4.1
dhcp-option=option:dns-server,8.8.8.8,8.8.4.4
bind-interfaces
EOL

# Create interface setup script
print_status "Creating interface setup script..."
cat > /usr/local/bin/setup_ap_interface.sh << EOL
#!/bin/bash

# Remove interface if it exists
iw dev uap0 del 2>/dev/null || true
sleep 1

# Reset wlan0
ip link set wlan0 down
iw wlan0 set type managed
ip link set wlan0 up
sleep 1

# Create new AP interface
iw dev wlan0 interface add uap0 type __ap
sleep 1

# Configure interface
ip link set uap0 up
ip addr flush dev uap0
ip addr add 192.168.4.1/24 dev uap0

# Enable IP forwarding
echo 1 > /proc/sys/net/ipv4/ip_forward

# Set up NAT
iptables -t nat -F
iptables -F FORWARD
iptables -t nat -A POSTROUTING -o wlan0 -j MASQUERADE
iptables -A FORWARD -i wlan0 -o uap0 -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i uap0 -o wlan0 -j ACCEPT
EOL

chmod +x /usr/local/bin/setup_ap_interface.sh

# Create systemd service for interface setup
print_status "Creating systemd services..."
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

# Make IP forwarding permanent
print_status "Making IP forwarding permanent..."
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/90-ip-forward.conf
sysctl -p /etc/sysctl.d/90-ip-forward.conf

# Make iptables rules persistent
print_status "Making iptables rules persistent..."
apt-get install -y iptables-persistent
mkdir -p /etc/iptables
iptables-save > /etc/iptables/rules.v4

# Set up proper permissions
print_status "Setting permissions..."
chmod 644 /etc/systemd/system/setup-ap-interface.service
chmod 755 /var/log/scale-reader || true
mkdir -p /var/log/scale-reader

# Enable services
print_status "Enabling services..."
systemctl daemon-reload
systemctl enable setup-ap-interface
systemctl enable hostapd
systemctl enable dnsmasq

# Start services in correct order
print_status "Starting services..."
systemctl start setup-ap-interface
sleep 2
systemctl start hostapd
sleep 2
systemctl start dnsmasq

# Verify services
print_status "Verifying services..."
for service in hostapd dnsmasq setup-ap-interface; do
    if systemctl is-active --quiet $service; then
        print_success "$service is running"
    else
        print_error "$service failed to start"
    fi
done

# Show interface status
print_status "Interface status:"
ip addr show uap0
iw dev uap0 info

# Final output
echo
print_success "Setup completed successfully!"
echo
echo "Access Point Details:"
echo "  SSID: ScaleSetup"
echo "  Password: scale12345"
echo "  IP Address: 192.168.4.1"
echo "  DHCP Range: 192.168.4.50 - 192.168.4.150"
echo
echo "To monitor the access point:"
echo "1. Check AP status:"
echo "   sudo iw dev uap0 info"
echo
echo "2. View connected clients:"
echo "   sudo iw dev uap0 station dump"
echo
echo "3. View service logs:"
echo "   sudo journalctl -u hostapd -f"
echo "   sudo journalctl -u dnsmasq -f"
echo
echo "To connect to the AP:"
echo "1. Look for 'ScaleSetup' in your WiFi networks"
echo "2. Connect using password: scale12345"
echo "3. Your device should receive an IP address in the range 192.168.4.50-150"