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

# 11. Create start script
info "Creating start script..."
cat > start.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python3 app.py
EOF
chmod +x start.sh
success "Start script created (./start.sh)"
echo ""

# 12. Installation complete
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Installation completed successfully!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${BLUE}Starting the server now...${NC}"
echo ""
echo -e "Access via: ${GREEN}http://${SERVER_IP}:29911/install${NC}"
echo ""
echo -e "${YELLOW}Press CTRL+C to stop the server${NC}"
echo ""
echo -e "To start the server later, run:"
echo -e "  ${GREEN}cd $INSTALL_PATH && ./start.sh${NC}"
echo ""

# 13. Start server
python3 app.py
