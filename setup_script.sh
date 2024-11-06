#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

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

# Function to show usage
usage() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  --scale-id STRING       Scale ID for the device"
    echo "  --username STRING       Username for authentication"
    echo "  --password STRING       Password for authentication"
    echo "  --serial-port STRING    Serial port for scale (default: /dev/ttyUSB0)"
    echo "  --baud-rate NUMBER      Baud rate for serial connection (default: 1200)"
    echo "  --source-dir STRING     Directory containing source files"
    exit 1
}

# Parse command line arguments
SERIAL_PORT="/dev/ttyUSB0"  # Default value
BAUD_RATE=1200             # Default value

while [[ $# -gt 0 ]]; do
    case $1 in
        --scale-id)
            SCALE_ID="$2"
            shift 2
            ;;
        --username)
            USERNAME="$2"
            shift 2
            ;;
        --password)
            PASSWORD="$2"
            shift 2
            ;;
        --serial-port)
            SERIAL_PORT="$2"
            shift 2
            ;;
        --baud-rate)
            BAUD_RATE="$2"
            shift 2
            ;;
        --source-dir)
            SOURCE_DIR="$2"
            shift 2
            ;;
        *)
            print_error "Unknown parameter: $1"
            usage
            ;;
    esac
done

# Validate required parameters
REQUIRED_PARAMS=(SCALE_ID USERNAME PASSWORD SOURCE_DIR)
for param in "${REQUIRED_PARAMS[@]}"; do
    if [ -z "${!param}" ]; then
        print_error "Missing required parameter: --${param,,}"
        usage
    fi
done

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "Please run as root (use sudo)"
    exit 1
fi

# Check if source directory exists
if [ ! -d "$SOURCE_DIR" ]; then
    print_error "Source directory not found: $SOURCE_DIR"
    exit 1
fi

# Check for required files
REQUIRED_FILES=("scale_reader.py" "authenticate.py" "periodic_commands.py" "auth_manager.py")
for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$SOURCE_DIR/$file" ]; then
        print_error "$file not found in source directory"
        exit 1
    fi
done

# Create necessary directories
print_status "Creating directories..."
mkdir -p /usr/local/bin
mkdir -p /etc/scale-reader
mkdir -p /var/log/scale-reader

# Create log files with proper permissions
touch /var/log/scale-reader/scale.log
touch /usr/local/bin/command_execution.log
chmod 644 /var/log/scale-reader/scale.log
chmod 644 /usr/local/bin/command_execution.log
chown root:root /var/log/scale-reader/scale.log
chown root:root /usr/local/bin/command_execution.log

# Copy scripts and ensure they have proper shebang
print_status "Copying and configuring scripts..."
for file in "${REQUIRED_FILES[@]}"; do
    # Copy file
    cp "$SOURCE_DIR/$file" "/usr/local/bin/"
    
    # Ensure file has shebang
    if ! grep -q "^#!/usr/bin/env python3" "/usr/local/bin/$file"; then
        sed -i '1i#!/usr/bin/env python3' "/usr/local/bin/$file"
    fi
    
    # Make executable
    chmod +x "/usr/local/bin/$file"
done

# Create configuration
print_status "Creating configuration..."
cat > /etc/scale-reader/config.json << EOL
{
    "scale_id": "$SCALE_ID",
    "serial_port": "$SERIAL_PORT",
    "baud_rate": $BAUD_RATE
}
EOL

# Set permissions
print_status "Setting permissions..."
chown -R root:root /etc/scale-reader
chmod 600 /etc/scale-reader/config.json
chown -R root:root /usr/local/bin
chmod 755 /usr/local/bin
chown -R root:root /var/log/scale-reader
chmod 755 /var/log/scale-reader

# Install required packages
print_status "Installing required packages..."
apt-get update
apt-get install -y python3-pip python3-venv python3-full

# Create a virtual environment
print_status "Creating Python virtual environment..."
VENV_PATH="/opt/scale-reader/venv"
mkdir -p /opt/scale-reader
python3 -m venv $VENV_PATH

# Install Python packages in virtual environment
print_status "Installing Python packages..."
$VENV_PATH/bin/pip install pyserial requests

# Create systemd service with virtual environment
print_status "Creating systemd service..."
cat > /etc/systemd/system/scale-reader.service << EOL
[Unit]
Description=Scale Reader Service
After=network.target

[Service]
Type=simple
ExecStart=$VENV_PATH/bin/python3 /usr/local/bin/periodic_commands.py
Restart=always
User=root
Environment=PYTHONPATH=/usr/local/bin
WorkingDirectory=/usr/local/bin

[Install]
WantedBy=multi-user.target
EOL

# Update periodic_commands.py to include correct paths
print_status "Updating script configurations..."
sed -i "s|'authenticate.py'|'/usr/local/bin/authenticate.py'|g" /usr/local/bin/periodic_commands.py
sed -i "s|'scale_reader.py'|'/usr/local/bin/scale_reader.py'|g" /usr/local/bin/periodic_commands.py

# Reload systemd and start service
print_status "Starting service..."
systemctl daemon-reload
systemctl enable scale-reader.service
systemctl stop scale-reader.service || true
sleep 2
systemctl start scale-reader.service

# Final instructions
echo
echo -e "${GREEN}Installation completed successfully!${NC}"
echo
echo "Configuration has been set up at:"
echo "  /etc/scale-reader/config.json"
echo
echo "You can monitor the logs in several ways:"
echo "1. Service logs:"
echo "  journalctl -u scale-reader -f"
echo
echo "2. Application logs:"
echo "  tail -f /var/log/scale-reader/scale.log"
echo "  tail -f /usr/local/bin/command_execution.log"
echo
echo "The scale reader service is running with scale ID: $SCALE_ID"
echo
echo "To check the service status:"
echo "  systemctl status scale-reader"