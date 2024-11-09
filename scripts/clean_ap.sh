#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${YELLOW}>>> $1${NC}"
}

# Stop all services
print_status "Stopping services..."
systemctl stop hostapd
systemctl stop dnsmasq
systemctl stop wifi-manager

# Disable services
print_status "Disabling services..."
systemctl disable hostapd
systemctl disable dnsmasq
systemctl disable wifi-manager
systemctl disable setup-ap-interface

# Remove custom services
print_status "Removing custom services..."
rm -f /etc/systemd/system/setup-ap-interface.service
rm -f /etc/systemd/system/wifi-manager.service

# Remove custom scripts
print_status "Removing custom scripts..."
rm -f /usr/local/bin/setup_ap_interface.sh
rm -f /usr/local/bin/wifi_manager.py

# Restore original configurations
print_status "Restoring original configurations..."
mv /etc/dnsmasq.conf.orig /etc/dnsmasq.conf 2>/dev/null || true
rm -f /etc/hostapd/hostapd.conf
rm -f /etc/default/hostapd

# Remove the interface
print_status "Removing AP interface..."
iw dev uap0 del 2>/dev/null || true

# Clean up iptables rules
print_status "Cleaning up iptables rules..."
iptables -t nat -F
iptables -F FORWARD
iptables-save > /etc/iptables/rules.v4

# Disable IP forwarding
print_status "Disabling IP forwarding..."
echo "0" > /proc/sys/net/ipv4/ip_forward
rm -f /etc/sysctl.d/90-ip-forward.conf

# Clean up logs
print_status "Cleaning up logs..."
rm -f /var/log/scale-reader/web.log
rmdir /var/log/scale-reader 2>/dev/null || true

# Reload systemd
print_status "Reloading systemd..."
systemctl daemon-reload

# Restart networking
print_status "Restarting networking..."
systemctl restart networking

echo
echo -e "${GREEN}Cleanup completed!${NC}"
echo
echo "The system has been restored to its original state."
echo "You may want to reboot the system to ensure all changes take effect:"
echo "  sudo reboot"