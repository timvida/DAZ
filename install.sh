#!/bin/bash

# GameServer Web Interface - Installation Script
# This script automatically downloads and installs the complete web interface

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# GitHub repository
REPO_URL="https://github.com/timvida/DAZ.git"
INSTALL_DIR="gameserver-webinterface"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   GameServer Web Interface - Installation Script         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Function for success messages
success() {
    echo -e "${GREEN}✓${NC} $1"
}

# Function for error messages
error() {
    echo -e "${RED}✗${NC} $1"
}

# Function for info messages
info() {
    echo -e "${YELLOW}→${NC} $1"
}

# Root check (do not run as root)
if [ "$EUID" -eq 0 ]; then
    error "Please DO NOT run this script as root!"
    echo "  Start it with: ./install.sh"
    exit 1
fi

# Detect operating system
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    error "Cannot detect operating system!"
    exit 1
fi

info "Detected operating system: $OS"
echo ""

# 1. Check and install Git
info "Checking for Git..."
if command -v git &> /dev/null; then
    success "Git is already installed"
else
    info "Installing Git..."
    if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
        sudo apt-get update
        sudo apt-get install -y git
    elif [ "$OS" = "centos" ] || [ "$OS" = "rhel" ]; then
        sudo yum install -y git
    else
        error "Automatic installation not supported for $OS!"
        echo "  Please install Git manually and run the script again."
        exit 1
    fi
    success "Git has been installed"
fi
echo ""

# 2. Clone repository
info "Downloading GameServer Web Interface from GitHub..."
if [ -d "$INSTALL_DIR" ]; then
    error "Directory '$INSTALL_DIR' already exists!"
    read -p "Do you want to delete it and reinstall? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$INSTALL_DIR"
        success "Old installation removed"
    else
        error "Installation cancelled"
        exit 1
    fi
fi

git clone "$REPO_URL" "$INSTALL_DIR"
if [ $? -eq 0 ]; then
    success "Repository cloned successfully"
else
    error "Failed to clone repository!"
    exit 1
fi
echo ""

# 3. Change to installation directory
cd "$INSTALL_DIR"
INSTALL_PATH=$(pwd)
info "Installation directory: $INSTALL_PATH"
echo ""

# 4. Check and install Python3
info "Checking for Python3..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    success "Python3 is already installed: $PYTHON_VERSION"
else
    info "Installing Python3..."
    if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
        sudo apt-get update
        sudo apt-get install -y python3 python3-pip python3-venv
    elif [ "$OS" = "centos" ] || [ "$OS" = "rhel" ]; then
        sudo yum install -y python3 python3-pip
    else
        error "Automatic installation not supported for $OS!"
        echo "  Please install Python3 manually and run the script again."
        exit 1
    fi
    success "Python3 has been installed"
fi
echo ""

# 5. Check pip
info "Checking for pip..."
if command -v pip3 &> /dev/null; then
    success "pip3 is already installed"
else
    info "Installing pip3..."
    if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
        sudo apt-get install -y python3-pip
    elif [ "$OS" = "centos" ] || [ "$OS" = "rhel" ]; then
        sudo yum install -y python3-pip
    fi
    success "pip3 has been installed"
fi
echo ""

# 6. Check and install SteamCMD
info "Checking for SteamCMD..."
if command -v steamcmd &> /dev/null; then
    success "SteamCMD is already installed"
else
    info "Installing SteamCMD..."

    # 32-bit libraries for SteamCMD
    if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
        sudo dpkg --add-architecture i386
        sudo apt-get update
        sudo apt-get install -y lib32gcc-s1 steamcmd || {
            info "Installing SteamCMD manually..."
            sudo apt-get install -y lib32gcc-s1 curl tar
            mkdir -p ~/steamcmd
            cd ~/steamcmd
            curl -sqL "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz" | tar zxvf -
            cd "$INSTALL_PATH"
            success "SteamCMD has been installed manually"
        }
    elif [ "$OS" = "centos" ] || [ "$OS" = "rhel" ]; then
        sudo yum install -y glibc.i686 libstdc++.i686 curl tar
        mkdir -p ~/steamcmd
        cd ~/steamcmd
        curl -sqL "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz" | tar zxvf -
        cd "$INSTALL_PATH"
    fi

    success "SteamCMD has been installed"
fi
echo ""

# 7. Create Python Virtual Environment
info "Creating Python Virtual Environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    success "Virtual Environment created"
else
    success "Virtual Environment already exists"
fi

# 8. Activate Virtual Environment and install dependencies
info "Installing Python dependencies..."
source venv/bin/activate
pip install --upgrade pip > /dev/null 2>&1

if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    if [ $? -eq 0 ]; then
        success "All Python dependencies have been installed"
    else
        error "Error installing dependencies!"
        exit 1
    fi
else
    error "requirements.txt not found!"
    exit 1
fi
echo ""

# 9. Get server IP address
info "Detecting server IP address..."
SERVER_IP=$(hostname -I | awk '{print $1}')
if [ -z "$SERVER_IP" ]; then
    SERVER_IP="localhost"
fi
success "Server IP: $SERVER_IP"
echo ""

# 10. Firewall notice
echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}  IMPORTANT: Firewall Configuration${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "  Make sure port 29911 is open in your firewall:"
echo ""
echo "  Ubuntu/Debian (ufw):"
echo "    sudo ufw allow 29911/tcp"
echo ""
echo "  CentOS/RHEL (firewalld):"
echo "    sudo firewall-cmd --permanent --add-port=29911/tcp"
echo "    sudo firewall-cmd --reload"
echo ""

# 11. Create management scripts in parent directory
info "Creating management scripts..."

# Go to parent directory
cd ..
PARENT_DIR=$(pwd)

# Create web_start.sh
cat > web_start.sh << 'EOF'
#!/bin/bash
# GameServer Web Interface - Start Script
# Starts the web interface in the background using nohup

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/gameserver-webinterface"

# Check if already running
if [ -f "webinterface.pid" ]; then
    PID=$(cat webinterface.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "Web interface is already running (PID: $PID)"
        exit 1
    else
        # PID file exists but process doesn't - clean up
        rm webinterface.pid
    fi
fi

# Activate virtual environment
source venv/bin/activate

# Start the web interface in background
nohup python3 app.py > webinterface.log 2>&1 &

# Save PID
echo $! > webinterface.pid

echo "Web interface started successfully!"
echo "PID: $(cat webinterface.pid)"
echo "Log file: webinterface.log"
echo ""
echo "To stop: ./web_stop.sh"
echo "To restart: ./web_restart.sh"
EOF
chmod +x web_start.sh

# Create web_stop.sh
cat > web_stop.sh << 'EOF'
#!/bin/bash
# GameServer Web Interface - Stop Script
# Stops the running web interface

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/gameserver-webinterface"

# Check if PID file exists
if [ ! -f "webinterface.pid" ]; then
    echo "Web interface is not running (no PID file found)"
    exit 1
fi

PID=$(cat webinterface.pid)

# Check if process is running
if ! ps -p $PID > /dev/null 2>&1; then
    echo "Web interface is not running (PID $PID not found)"
    rm webinterface.pid
    exit 1
fi

# Stop the process
echo "Stopping web interface (PID: $PID)..."
kill $PID

# Wait for process to terminate
sleep 2

# Force kill if still running
if ps -p $PID > /dev/null 2>&1; then
    echo "Force killing process..."
    kill -9 $PID
    sleep 1
fi

# Clean up PID file
rm webinterface.pid

echo "Web interface stopped successfully!"
EOF
chmod +x web_stop.sh

# Create web_restart.sh
cat > web_restart.sh << 'EOF'
#!/bin/bash
# GameServer Web Interface - Restart Script
# Stops and restarts the web interface

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Restarting web interface..."
echo ""

# Stop if running
./web_stop.sh 2>/dev/null
echo ""
sleep 2

# Start
./web_start.sh
EOF
chmod +x web_restart.sh

# Create update.sh
cat > update.sh << 'EOF'
#!/bin/bash
# GameServer Web Interface - Update Script
# Updates the web interface from Git repository

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/gameserver-webinterface"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   GameServer Web Interface - Update                      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if git repo
if [ ! -d ".git" ]; then
    echo -e "${RED}✗${NC} Not a Git repository. Initializing..."
    git init
    git remote add origin https://github.com/timvida/DAZ.git
    git fetch origin
    git checkout -b main origin/main || git branch -M main && git branch --set-upstream-to=origin/main
fi

# Check for updates
echo -e "${YELLOW}→${NC} Checking for updates..."
git fetch origin

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
COMMITS_BEHIND=$(git rev-list --count HEAD..origin/$CURRENT_BRANCH)

if [ "$COMMITS_BEHIND" -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Already up to date!"
    exit 0
fi

echo -e "${GREEN}✓${NC} $COMMITS_BEHIND update(s) available"
echo ""
echo "Changes:"
git log --oneline HEAD..origin/$CURRENT_BRANCH | head -5
echo ""

# Confirm update
read -p "Do you want to update now? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Update cancelled."
    exit 0
fi

# Stop web interface if running
echo -e "${YELLOW}→${NC} Stopping web interface..."
cd "$SCRIPT_DIR"
./web_stop.sh 2>/dev/null || true

cd "$SCRIPT_DIR/gameserver-webinterface"

# Stash local changes
echo -e "${YELLOW}→${NC} Saving local changes..."
git stash push -u -m "Auto-stash before update" 2>/dev/null || true

# Pull updates
echo -e "${YELLOW}→${NC} Downloading updates..."
git pull origin $CURRENT_BRANCH

# Update dependencies
echo -e "${YELLOW}→${NC} Updating dependencies..."
source venv/bin/activate
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt > /dev/null 2>&1

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Update completed successfully!                         ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Restart web interface
echo -e "${BLUE}→${NC} Restarting web interface..."
cd "$SCRIPT_DIR"
./web_start.sh

echo ""
echo -e "${GREEN}✓${NC} Update complete and web interface restarted!"
EOF
chmod +x update.sh

cd "$INSTALL_PATH"
success "Management scripts created in parent directory:"
echo "  - web_start.sh   (Start the web interface)"
echo "  - web_stop.sh    (Stop the web interface)"
echo "  - web_restart.sh (Restart the web interface)"
echo "  - update.sh      (Update from Git)"
echo ""

# 12. Installation complete
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Installation completed successfully!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${BLUE}Starting the web interface now...${NC}"
echo ""
echo -e "Access via: ${GREEN}http://${SERVER_IP}:29911/install${NC}"
echo ""
echo -e "${YELLOW}Press CTRL+C to stop the server${NC}"
echo ""
echo -e "Management commands:"
echo -e "  Start:   ${GREEN}cd $PARENT_DIR && ./web_start.sh${NC}"
echo -e "  Stop:    ${GREEN}cd $PARENT_DIR && ./web_stop.sh${NC}"
echo -e "  Restart: ${GREEN}cd $PARENT_DIR && ./web_restart.sh${NC}"
echo -e "  Update:  ${GREEN}cd $PARENT_DIR && ./update.sh${NC}"
echo ""

# 13. Start server directly for initial setup
cd "$INSTALL_PATH"
source venv/bin/activate
python3 app.py
