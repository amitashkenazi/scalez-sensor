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
    curl \
    cron

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

# Configure cron jobs
print_status "Configuring cron jobs..."

# Create a temporary cron file
cat > /tmp/scale_crontab << EOL
# Scale Reader cron jobs
# Take measurement every 5 minutes (adjust interval as needed)
*/5 * * * * /opt/scale-reader/venv/bin/python3 /usr/local/bin/scale_reader.py

# Log rotation and cleanup daily at 1 AM
0 1 * * * find /var/log/scale-reader -name "*.log" -mtime +7 -exec rm {} \;

# Monitor disk space weekly and clean up if over 80%
0 2 * * 0 df -h / | awk '{use=$5} END{if(use>80){system("journalctl --vacuum-size=500M")}}'
EOL

# Install new cron jobs
crontab -u root /tmp/scale_crontab

# Remove temporary file
rm /tmp/scale_crontab

# Verify cron installation
if crontab -l | grep -q "scale_reader.py"; then
    print_success "Cron jobs installed successfully"
else
    print_error "Failed to install cron jobs"
fi

# Create helper script for managing cron interval
cat > /usr/local/bin/scale-interval << EOL
#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "\${YELLOW}>>> \$1\${NC}"
}

print_success() {
    echo -e "\${GREEN}✓ \$1\${NC}"
}

print_error() {
    echo -e "\${RED}✗ \$1\${NC}"
}

show_usage() {
    echo "Usage: \$0 <minutes>"
    echo "Example: \$0 15    # Sets interval to 15 minutes"
    echo "Current interval: \$(crontab -l | grep 'scale_reader.py' | cut -d' ' -f1 | tr -d '*/')"
    exit 1
}

if [ "\$1" = "-h" ] || [ "\$1" = "--help" ]; then
    show_usage
fi

# Validate input
if ! [[ "\$1" =~ ^[0-9]+$ ]] || [ "\$1" -lt 1 ] || [ "\$1" -gt 1440 ]; then
    print_error "Please provide a valid interval in minutes (1-1440)"
    show_usage
fi

# Backup existing crontab
crontab -l > /tmp/current_crontab

# Update the scale reader interval
sed -i "/scale_reader.py/c\\*\/\$1 * * * * /opt/scale-reader/venv/bin/python3 /usr/local/bin/scale_reader.py" /tmp/current_crontab

# Install updated crontab
if crontab /tmp/current_crontab; then
    print_success "Measurement interval updated to \$1 minutes"
else
    print_error "Failed to update crontab"
fi

# Cleanup
rm /tmp/current_crontab
EOL

# Make the helper script executable
chmod +x /usr/local/bin/scale-interval

# Set proper permissions
print_status "Setting permissions..."
chmod 644 /etc/systemd/system/scale-reader.service
chmod 644 /etc/systemd/system/cloud-control.service
chmod -R 755 /var/log/scale-reader
chmod -R 755 /opt/scale-reader
touch /var/log/scale-reader/scale.log
chmod 644 /var/log/scale-reader/scale.log

# Set up log rotation
print_status "Setting up log rotation..."
cat > /etc/logrotate.d/scale-reader << EOL
/var/log/scale-reader/scale.log {
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

# Create udev rule for USB serial device
print_status "Creating udev rule for USB serial device..."
cat > /etc/udev/rules.d/99-usb-scale.rules << EOL
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", SYMLINK+="ttyUSB0", MODE="0666"
ACTION=="add", SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", RUN+="/bin/systemctl restart scale-reader.service"
EOL

check_status "udev rule creation"

# Reload udev rules
print_status "Reloading udev rules..."
udevadm control --reload-rules
udevadm trigger

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
echo "Cron Job Configuration:"
echo "  Current measurement interval: $(crontab -l | grep 'scale_reader.py' | cut -d' ' -f1 | tr -d '*/') minutes"
echo
echo "To change measurement interval:"
echo "  scale-interval <minutes>"
echo "  Example: scale-interval 15    # Sets interval to 15 minutes"
echo
echo "To view cron job status:"
echo "  grep CRON /var/log/syslog"
echo
echo "To view scale readings:"
echo "  tail -f /var/log/scale-reader/scale.log"
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
systemctl status scale-reader.service --no-pager || true