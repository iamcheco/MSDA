#!/bin/bash

# IoT System Setup Script for Raspberry Pi running AlmaLinux
# This script installs dependencies and configures the system

set -e

echo "========================================"
echo "IoT System Setup for AlmaLinux"
echo "========================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   print_warning "This script should not be run as root for security reasons"
   print_warning "It will use sudo when necessary"
   exit 1
fi

# Update system
print_status "Updating system packages..."
sudo dnf update -y

# Install Python and pip
print_status "Installing Python 3 and pip..."
sudo dnf install -y python3 python3-pip python3-devel

# Install development tools
print_status "Installing development tools..."
sudo dnf groupinstall -y "Development Tools"
sudo dnf install -y gcc gcc-c++ make

# Install Git
print_status "Installing Git..."
sudo dnf install -y git

# Install SQLite
print_status "Installing SQLite..."
sudo dnf install -y sqlite sqlite-devel

# Install Arduino CLI (for uploading sketches)
print_status "Installing Arduino CLI..."
curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh
sudo mv bin/arduino-cli /usr/local/bin/
rmdir bin

# Configure Arduino CLI
print_status "Configuring Arduino CLI..."
arduino-cli config init
arduino-cli core update-index
arduino-cli core install arduino:avr

# Install required Arduino libraries
print_status "Installing Arduino libraries..."
arduino-cli lib install "DHT sensor library"
arduino-cli lib install "OneWire"
arduino-cli lib install "DallasTemperature"
arduino-cli lib install "Adafruit BMP280 Library"

# Create project directory
PROJECT_DIR="$HOME/iot_system"
print_status "Creating project directory at $PROJECT_DIR..."
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# Create Python virtual environment
print_status "Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
print_status "Installing Python dependencies..."
pip install --upgrade pip
pip install pyserial
pip install sqlite3-to-mysql  # Optional for MySQL export

# Create requirements.txt
cat > requirements.txt << 'EOF'
pyserial>=3.5
EOF

pip install -r requirements.txt

# Create the Python IoT management script
print_status "Creating Python IoT management script..."
cat > iot_manager.py << 'PYTHON_SCRIPT'
# [The full Python script content would go here]
# Due to length, please copy the Python script from the artifact above
PYTHON_SCRIPT

# Create Arduino sketch directory
mkdir -p arduino_sketch
cat > arduino_sketch/arduino_sketch.ino << 'ARDUINO_SKETCH'
# [The full Arduino sketch content would go here]
# Due to length, please copy the Arduino sketch from the artifact above
ARDUINO_SKETCH

# Create systemd service file for auto-start
print_status "Creating systemd service..."
sudo tee /etc/systemd/system/iot-manager.service > /dev/null << EOF
[Unit]
Description=IoT Sensor Management System
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$PROJECT_DIR/venv/bin/python $PROJECT_DIR/iot_manager.py --daemon
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Create udev rule for Arduino serial port
print_status "Creating udev rule for Arduino..."
sudo tee /etc/udev/rules.d/99-arduino.rules > /dev/null << 'EOF'
# Arduino Nano
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", SYMLINK+="arduino", MODE="0666"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", SYMLINK+="arduino", MODE="0666"
SUBSYSTEM=="tty", ATTRS{idVendor}=="2341", ATTRS{idProduct}=="0043", SYMLINK+="arduino", MODE="0666"
EOF

# Reload udev rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# Add user to dialout group for serial access
print_status "Adding user to dialout group..."
sudo usermod -a -G dialout $USER

# Create configuration file
print_status "Creating default configuration..."
cat > iot_config.ini << 'EOF'
[SERIAL]
port = /dev/ttyUSB0
baudrate = 115200
timeout = 1

[DATABASE]
path = iot_sensors.db
retention_days = 30
backup_enabled = true
backup_interval_hours = 24

[MONITORING]
sensor_read_interval = 2000
heartbeat_timeout = 30
auto_reconnect = true
max_reconnect_attempts = 10

[ALERTS]
enabled = true
temp_min = -10
temp_max = 50
humidity_min = 20
humidity_max = 80
distance_min = 5
distance_max = 200

[LOGGING]
level = INFO
file = iot_system.log
max_size_mb = 100
backup_count = 5

[API]
enabled = false
host = 0.0.0.0
port = 8080
EOF

# Create helper scripts
print_status "Creating helper scripts..."

# Start script
cat > start_iot.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python iot_manager.py
EOF
chmod +x start_iot.sh

# Upload Arduino sketch script
cat > upload_sketch.sh << 'EOF'
#!/bin/bash
BOARD="arduino:avr:nano"
PORT=$(ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | head -n1)

if [ -z "$PORT" ]; then
    echo "No Arduino found. Please connect your Arduino Nano."
    exit 1
fi

echo "Compiling and uploading to Arduino Nano on $PORT..."
arduino-cli compile --fqbn $BOARD arduino_sketch/
arduino-cli upload -p $PORT --fqbn $BOARD arduino_sketch/
echo "Upload complete!"
EOF
chmod +x upload_sketch.sh

# Monitor script
cat > monitor.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
tail -f iot_system.log
EOF
chmod +x monitor.sh

# Database query script
cat > query_db.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
sqlite3 iot_sensors.db "$1"
EOF
chmod +x query_db.sh

# Create web dashboard (optional, basic HTML)
print_status "Creating web dashboard template..."
mkdir -p web
cat > web/dashboard.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>IoT Sensor Dashboard</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background: #f0f0f0;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            text-align: center;
        }
        .sensor-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        .sensor-card {
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .sensor-name {
            font-weight: bold;
            color: #2196F3;
            margin-bottom: 10px;
        }
        .sensor-value {
            font-size: 24px;
            color: #333;
        }
        .sensor-unit {
            color: #666;
            font-size: 14px;
        }
        .sensor-time {
            color: #999;
            font-size: 12px;
            margin-top: 10px;
        }
        .status {
            padding: 10px;
            background: #4CAF50;
            color: white;
            border-radius: 5px;
            text-align: center;
            margin-bottom: 20px;
        }
        .offline {
            background: #f44336;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>IoT Sensor Dashboard</h1>
        <div class="status" id="status">System Status: Online</div>
        <div class="sensor-grid" id="sensors">
            <!-- Sensor data will be loaded here -->
        </div>
    </div>
    
    <script>
        // This is a template - you would need to implement the API endpoint
        // to fetch real-time data from your Python backend
        
        function loadSensorData() {
            // Example placeholder - replace with actual API call
            const sensors = document.getElementById('sensors');
            sensors.innerHTML = '<div class="sensor-card"><div class="sensor-name">Loading...</div></div>';
            
            // In production, fetch from your API:
            // fetch('/api/sensors')
            //     .then(response => response.json())
            //     .then(data => updateDashboard(data));
        }
        
        // Refresh every 5 seconds
        setInterval(loadSensorData, 5000);
        loadSensorData();
    </script>
</body>
</html>
EOF

# Final setup instructions
print_status "Setup complete!"
echo ""
echo "========================================"
echo "NEXT STEPS:"
echo "========================================"
echo ""
echo "1. Connect your Arduino Nano to the Raspberry Pi via USB"
echo ""
echo "2. Upload the Arduino sketch:"
echo "   cd $PROJECT_DIR"
echo "   ./upload_sketch.sh"
echo ""
echo "3. Find your Arduino's serial port:"
echo "   ls /dev/ttyUSB* /dev/ttyACM*"
echo ""
echo "4. Update the serial port in iot_config.ini if needed"
echo ""
echo "5. Start the IoT manager:"
echo "   ./start_iot.sh"
echo ""
echo "6. Or enable auto-start on boot:"
echo "   sudo systemctl enable iot-manager.service"
echo "   sudo systemctl start iot-manager.service"
echo ""
echo "7. Monitor the system:"
echo "   ./monitor.sh"
echo ""
echo "8. Query the database:"
echo "   ./query_db.sh \"SELECT * FROM sensors;\""
echo ""
print_warning "Note: You may need to log out and back in for serial port access to work"
echo ""
echo "========================================"
echo "TROUBLESHOOTING:"
echo "========================================"
echo ""
echo "If serial port doesn't work:"
echo "  - Check: ls /dev/tty*"
echo "  - Update port in iot_config.ini"
echo "  - Ensure you're in dialout group: groups $USER"
echo ""
echo "If Arduino libraries fail to install:"
echo "  - Manually install in Arduino IDE"
echo "  - Or use: arduino-cli lib search <library_name>"
echo ""
echo "For logs:"
echo "  - tail -f $PROJECT_DIR/iot_system.log"
echo "  - journalctl -u iot-manager.service -f"
echo ""