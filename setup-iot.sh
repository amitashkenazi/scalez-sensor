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

# Function to check command status
check_status() {
    if [ $? -eq 0 ]; then
        print_success "$1"
    else
        print_error "$1"
        exit 1
    fi
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "Please run as root (use sudo)"
    exit 1
fi

# Create necessary directories
print_status "Creating directories..."
mkdir -p /usr/local/bin
mkdir -p /etc/scale-reader
mkdir -p /var/log/scale-reader
mkdir -p /etc/scale-reader/certs
mkdir -p /opt/scale-reader

check_status "Directory creation"

# Install required system packages
print_status "Installing required system packages..."
apt-get update
apt-get install -y \
    python3-venv \
    python3-dev \
    python3-pip \
    python3-serial \
    cmake \
    git \
    build-essential \
    udev \
    vim \
    wget \
    curl

check_status "System package installation"

# Create and configure virtual environment
print_status "Creating Python virtual environment..."
python3 -m venv /opt/scale-reader/venv

check_status "Virtual environment creation"

# Activate virtual environment and install packages
print_status "Installing Python packages in virtual environment..."
/opt/scale-reader/venv/bin/pip install --upgrade pip
/opt/scale-reader/venv/bin/pip install \
    awsiotsdk \
    pyserial \
    boto3 \
    psutil

check_status "Python package installation"

# Copy scale reader script
print_status "Installing scale reader script..."
cp scale_reader.py /usr/local/bin/
chmod +x /usr/local/bin/scale_reader.py

check_status "Scale reader script installation"

# Install cloud control script
print_status "Installing cloud control script..."
cp cloud_control.py /opt/scale-reader/
chmod +x /opt/scale-reader/cloud_control.py

check_status "Cloud control script installation"

# Create systemd services
print_status "Creating systemd services..."

# Scale reader service
cat > /etc/systemd/system/scale-reader.service << EOL
[Unit]
Description=Scale Reader Service
After=network.target

[Service]
Type=simple
ExecStart=/opt/scale-reader/venv/bin/python3 /usr/local/bin/scale_reader.py
Restart=always
RestartSec=10
User=root
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPATH=/opt/scale-reader/venv/lib/python3.9/site-packages
Environment=PATH=/opt/scale-reader/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
WorkingDirectory=/usr/local/bin

[Install]
WantedBy=multi-user.target
EOL

# Cloud control service
cat > /etc/systemd/system/cloud-control.service << EOL
[Unit]
Description=Cloud Control Service
After=network.target
Wants=scale-reader.service

[Service]
Type=simple
ExecStart=/opt/scale-reader/venv/bin/python3 /opt/scale-reader/cloud_control.py
Restart=always
RestartSec=10
User=root
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPATH=/opt/scale-reader/venv/lib/python3.9/site-packages
Environment=PATH=/opt/scale-reader/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
WorkingDirectory=/opt/scale-reader

[Install]
WantedBy=multi-user.target
EOL

check_status "Service creation"

# Create config template if it doesn't exist
if [ ! -f /etc/scale-reader/config.json ]; then
    print_status "Creating configuration template..."
    cat > /etc/scale-reader/config.json << EOL
{
    "scale_id": "YOUR_SCALE_ID",
    "serial_port": "/dev/ttyUSB0",
    "baud_rate": 1200,
    "iot_endpoint": "YOUR_IOT_ENDPOINT"
}
EOL
fi

# Add udev rule for USB serial device
print_status "Creating udev rule for USB serial device..."
cat > /etc/udev/rules.d/99-usb-scale.rules << EOL
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", SYMLINK+="ttyUSB0", MODE="0666"
ACTION=="add", SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", RUN+="/bin/systemctl restart scale-reader.service"
EOL

check_status "udev rule creation"

# Set proper permissions
print_status "Setting permissions..."
chmod 644 /etc/systemd/system/scale-reader.service
chmod 644 /etc/systemd/system/cloud-control.service
chmod 600 /etc/scale-reader/config.json
chmod -R 755 /var/log/scale-reader
chmod -R 755 /opt/scale-reader
touch /var/log/scale-reader/scale.log
touch /var/log/scale-reader/cloud-control.log
chmod 644 /var/log/scale-reader/scale.log
chmod 644 /var/log/scale-reader/cloud-control.log

# Set up log rotation
print_status "Setting up log rotation..."
cat > /etc/logrotate.d/scale-reader << EOL
/var/log/scale-reader/scale.log /var/log/scale-reader/cloud-control.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
}
EOL

check_status "Log rotation setup"

# Reload udev rules
print_status "Reloading udev rules..."
udevadm control --reload-rules
udevadm trigger

# Create helper scripts
print_status "Creating helper scripts..."

# Create log viewer script
cat > /usr/local/bin/scale-logs << EOL
#!/bin/bash
case "\$1" in
    scale)
        sudo journalctl -u scale-reader -f
        ;;
    cloud)
        sudo journalctl -u cloud-control -f
        ;;
    *)
        echo "Usage: \$0 {scale|cloud}"
        exit 1
esac
EOL

# Create service control script
cat > /usr/local/bin/scale-service << EOL
#!/bin/bash
SERVICE=\$1
ACTION=\$2

case "\$SERVICE" in
    scale)
        SERVICE_NAME="scale-reader"
        ;;
    cloud)
        SERVICE_NAME="cloud-control"
        ;;
    *)
        echo "Usage: \$0 {scale|cloud} {start|stop|restart|status}"
        exit 1
        ;;
esac

case "\$ACTION" in
    start|stop|restart|status)
        sudo systemctl \$ACTION \$SERVICE_NAME
        ;;
    *)
        echo "Usage: \$0 {scale|cloud} {start|stop|restart|status}"
        exit 1
        ;;
esac
EOL

chmod +x /usr/local/bin/scale-logs
chmod +x /usr/local/bin/scale-service

check_status "Helper script creation"

# Enable services
print_status "Enabling services..."
systemctl daemon-reload
systemctl enable scale-reader.service
systemctl enable cloud-control.service

check_status "Service enablement"

print_success "Setup completed successfully!"
echo
echo "Before starting the services, please:"
echo
echo "1. Update the configuration in /etc/scale-reader/config.json with your values:"
echo "   sudo nano /etc/scale-reader/config.json"
echo
echo "2. Copy your AWS IoT certificates to /etc/scale-reader/certs:"
echo "   - device.cert.pem"
echo "   - device.private.key"
echo "   - root-CA.crt"
echo
echo "3. Ensure your scale is connected via USB"
echo
echo "Useful commands:"
echo "Start/stop services:    scale-service {scale|cloud} {start|stop|restart|status}"
echo "View logs:              scale-logs {scale|cloud}"
echo "Edit config:            sudo nano /etc/scale-reader/config.json"
echo "View USB devices:       ls -l /dev/ttyUSB*"
echo
echo "Certificate locations:"
echo "Config directory:       /etc/scale-reader/"
echo "Certificate directory:  /etc/scale-reader/certs/"
echo "Log directory:         /var/log/scale-reader/"
echo
print_status "Testing USB serial port detection..."
ls -l /dev/ttyUSB* 2>/dev/null || echo "No USB serial devices found yet"
echo
print_status "Current service status:"
systemctl status scale-reader.service || true
systemctl status cloud-control.service || true