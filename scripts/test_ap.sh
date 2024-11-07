#!/bin/bash

# Stop existing services
sudo systemctl stop hostapd
sudo systemctl stop dnsmasq

# Create basic hostapd configuration
sudo tee /etc/hostapd/hostapd.conf > /dev/null << EOL
interface=uap0
driver=nl80211
ssid=ScaleTest
hw_mode=g
channel=6
auth_algs=1
wpa=2
wpa_passphrase=testpassword123
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
country_code=US
EOL

# Set correct permissions
sudo chmod 600 /etc/hostapd/hostapd.conf

# Configure default hostapd
echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' | sudo tee /etc/default/hostapd

# Try running hostapd directly to see any errors
echo "Testing hostapd directly. Press Ctrl+C to stop after a few seconds..."
sudo hostapd -dd /etc/hostapd/hostapd.conf
EOL