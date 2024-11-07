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

# Function to ensure wireless interface is ready
ensure_wireless_ready() {
    local max_attempts=5
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        print_status "Checking wireless interface (attempt $attempt/$max_attempts)..."
        
        # Make sure interface exists
        if ! ip link show wlan0 >/dev/null 2>&1; then
            print_error "wlan0 interface not found"
            return 1
        fi
        
        # Check if wireless extensions are available
        if iwconfig wlan0 >/dev/null 2>&1; then
            print_success "Wireless interface is ready"
            return 0
        fi
        
        print_status "Waiting for wireless interface to be ready..."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    print_error "Wireless interface failed to initialize"
    return 1
}

# Function to create and configure AP interface
setup_ap_interface() {
    local max_attempts=3
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        print_status "Setting up AP interface (attempt $attempt/$max_attempts)..."
        
        # Remove existing AP interface if it exists
        iw dev uap0 del 2>/dev/null || true
        sleep 2
        
        # Reset wlan0
        ip link set wlan0 down
        sleep 1
        iw wlan0 set type managed
        sleep 1
        ip link set wlan0 up
        sleep 2
        
        # Create new AP interface
        if ! iw dev wlan0 interface add uap0 type __ap; then
            print_error "Failed to create uap0 interface"
            attempt=$((attempt + 1))
            continue
        fi
        
        sleep 2
        
        # Configure interface
        ip link set uap0 up
        sleep 1
        ip addr flush dev uap0
        sleep 1
        if ip addr add 192.168.4.1/24 dev uap0; then
            print_success "AP interface configured successfully"
            return 0
        fi
        
        attempt=$((attempt + 1))
    done
    
    print_error "Failed to configure AP interface after $max_attempts attempts"
    return 1
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "Please run as root (use sudo)"
    exit 1
fi

# Install required packages
print_status "Installing required packages..."
apt-get update
apt-get install -y hostapd dnsmasq python3-flask python3-pip wireless-tools wpasupplicant net-tools

# Stop and disable potentially conflicting services
print_status "Stopping and disabling conflicting services..."
systemctl stop systemd-resolved
systemctl disable systemd-resolved
systemctl stop hostapd
systemctl stop dnsmasq
systemctl stop wpa_supplicant

# Unmask and enable hostapd
systemctl unmask hostapd
systemctl unmask hostapd.service

# Unblock wifi
print_status "Unblocking WiFi..."
rfkill unblock wifi
sleep 2

# Ensure wireless interface is ready
if ! ensure_wireless_ready; then
    print_error "Failed to initialize wireless interface"
    exit 1
fi

# Set up AP interface
if ! setup_ap_interface; then
    print_error "Failed to set up AP interface"
    # Show debugging information
    print_status "Debug information:"
    echo "Wireless interfaces:"
    iw dev
    echo "Network interfaces:"
    ip addr
    echo "RF Kill status:"
    rfkill list
    exit 1
fi

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
if [ -f /etc/dnsmasq.conf ]; then
    cp /etc/dnsmasq.conf /etc/dnsmasq.conf.orig
fi

cat > /etc/dnsmasq.conf << EOL
interface=uap0
bind-interfaces
dhcp-range=192.168.4.50,192.168.4.150,255.255.255.0,24h
dhcp-option=option:router,192.168.4.1
dhcp-option=option:dns-server,8.8.8.8,8.8.4.4
log-queries
log-dhcp
EOL

chmod 644 /etc/dnsmasq.conf
chown root:root /etc/dnsmasq.conf

# Enable IP forwarding
print_status "Configuring IP forwarding..."
echo 1 > /proc/sys/net/ipv4/ip_forward
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/90-ip-forward.conf
sysctl -p /etc/sysctl.d/90-ip-forward.conf

# Set up NAT rules
print_status "Configuring NAT..."
iptables -t nat -F
iptables -F FORWARD
iptables -t nat -A POSTROUTING -o wlan0 -j MASQUERADE
iptables -A FORWARD -i wlan0 -o uap0 -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i uap0 -o wlan0 -j ACCEPT

# Make iptables rules persistent
apt-get install -y iptables-persistent
mkdir -p /etc/iptables
iptables-save > /etc/iptables/rules.v4

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
ExecStart=/bin/bash -c 'rfkill unblock wifi; \
    ip link set wlan0 down; \
    sleep 1; \
    iw wlan0 set type managed; \
    sleep 1; \
    ip link set wlan0 up; \
    sleep 2; \
    iw dev uap0 del 2>/dev/null || true; \
    sleep 1; \
    iw dev wlan0 interface add uap0 type __ap; \
    sleep 2; \
    ip link set uap0 up; \
    ip addr add 192.168.4.1/24 dev uap0; \
    echo 1 > /proc/sys/net/ipv4/ip_forward; \
    iptables -t nat -A POSTROUTING -o wlan0 -j MASQUERADE; \
    iptables -A FORWARD -i wlan0 -o uap0 -m state --state RELATED,ESTABLISHED -j ACCEPT; \
    iptables -A FORWARD -i uap0 -o wlan0 -j ACCEPT'

[Install]
WantedBy=multi-user.target
EOL

chmod 644 /etc/systemd/system/setup-ap-interface.service

# Enable and start services
print_status "Starting services..."
systemctl daemon-reload
systemctl enable setup-ap-interface
systemctl enable hostapd
systemctl enable dnsmasq

# Start services in order with proper delays
systemctl start setup-ap-interface
sleep 5

if ! ip addr show uap0 | grep -q "192.168.4.1/24"; then
    print_error "Failed to verify uap0 interface configuration"
    echo "Current interface status:"
    ip addr show
    exit 1
fi

systemctl start hostapd
sleep 3
systemctl start dnsmasq
sleep 3

# Verify all services
print_status "Verifying services..."
for service in hostapd dnsmasq; do
    if systemctl is-active --quiet $service; then
        print_success "$service is running"
    else
        print_error "$service failed to start"
        echo "Service status:"
        systemctl status $service
    fi
done

# Show current status
print_status "Current network status:"
ip addr show uap0
echo
print_status "Current hostapd status:"
systemctl status hostapd
echo
print_success "Setup completed!"
echo
echo "Access Point Details:"
echo "  SSID: ScaleSetup"
echo "  Password: scale12345"
echo "  IP Address: 192.168.4.1"
echo "  DHCP Range: 192.168.4.50 - 192.168.4.150"