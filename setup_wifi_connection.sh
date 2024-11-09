#!/bin/bash

# Create the wpa_supplicant configuration store directory
sudo mkdir -p /etc/scale-reader/wifi/
sudo chmod 755 /etc/scale-reader/wifi/

# Create the reconnect script
cat > /usr/local/bin/wifi_reconnect.sh << 'EOL'
#!/bin/bash

WIFI_STORE="/etc/scale-reader/wifi/last_connection.conf"

if [ -f "$WIFI_STORE" ]; then
    # Get stored credentials
    source "$WIFI_STORE"
    
    if [ ! -z "$SSID" ] && [ ! -z "$PASSWORD" ]; then
        # Wait for interface to be ready
        sleep 10
        
        # Try to connect using stored credentials
        /usr/local/bin/connect_to_wifi.sh -i wlan0 -s "$SSID" -p "$PASSWORD"
    fi
fi
EOL

chmod +x /usr/local/bin/wifi_reconnect.sh

# Create systemd service
cat > /etc/systemd/system/wifi-connection.service << 'EOL'
[Unit]
Description=WiFi Connection Service
After=network.target hostapd.service
Wants=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/wifi_reconnect.sh

[Install]
WantedBy=multi-user.target
EOL

# Enable the service
systemctl daemon-reload
systemctl enable wifi-connection.service