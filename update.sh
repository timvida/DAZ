#!/bin/bash
# DayZ Server Manager - Manual Update Script
# This script performs a manual update of the web interface

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================"
echo "DayZ Server Manager - Update Script"
echo "======================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if git is installed
if ! command -v git &> /dev/null; then
    echo -e "${RED}Error: Git is not installed!${NC}"
    echo "Please install git: sudo apt-get install git"
    exit 1
fi

# Check if this is a git repository
if [ ! -d ".git" ]; then
    echo -e "${YELLOW}This is not a Git repository yet.${NC}"
    echo -e "${BLUE}Initializing Git repository...${NC}"

    read -p "Enter the Git repository URL (or press Enter to skip): " REPO_URL

    if [ -n "$REPO_URL" ]; then
        # Backup current files
        echo -e "${BLUE}Creating backup...${NC}"
        BACKUP_DIR="../webinterface-backup-$(date +%Y%m%d-%H%M%S)"
        mkdir -p "$BACKUP_DIR"
        cp -r . "$BACKUP_DIR" 2>/dev/null || true
        echo -e "${GREEN}Backup created at: $BACKUP_DIR${NC}"

        # Initialize git
        git init
        git remote add origin "$REPO_URL"
        git fetch origin

        # Determine default branch
        DEFAULT_BRANCH=$(git remote show origin | grep 'HEAD branch' | cut -d' ' -f5)
        if [ -z "$DEFAULT_BRANCH" ]; then
            DEFAULT_BRANCH="main"
        fi

        echo -e "${BLUE}Using branch: $DEFAULT_BRANCH${NC}"
        git checkout -b "$DEFAULT_BRANCH" origin/"$DEFAULT_BRANCH" || git checkout "$DEFAULT_BRANCH"

        echo -e "${GREEN}Git repository initialized!${NC}"
    else
        echo -e "${YELLOW}Skipping Git initialization.${NC}"
        echo "To manually initialize later, run:"
        echo "  git init"
        echo "  git remote add origin <repository-url>"
        echo "  git pull origin main"
        exit 0
    fi
else
    echo -e "${BLUE}Checking for updates...${NC}"

    # Get current branch
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
    echo "Current branch: $CURRENT_BRANCH"

    # Check for local changes
    if [[ -n $(git status -s) ]]; then
        echo -e "${YELLOW}Warning: You have local changes!${NC}"
        git status -s
        echo ""
        read -p "Do you want to stash these changes before updating? (y/n): " STASH_CHOICE

        if [ "$STASH_CHOICE" = "y" ] || [ "$STASH_CHOICE" = "Y" ]; then
            echo -e "${BLUE}Stashing local changes...${NC}"
            git stash push -u -m "Auto-stash before update at $(date)"
            echo -e "${GREEN}Changes stashed!${NC}"
        else
            echo -e "${YELLOW}Continuing without stashing...${NC}"
        fi
    fi

    # Fetch updates
    echo -e "${BLUE}Fetching updates from remote...${NC}"
    git fetch origin

    # Check if behind
    LOCAL=$(git rev-parse @)
    REMOTE=$(git rev-parse @{u} 2>/dev/null || echo "")

    if [ -z "$REMOTE" ]; then
        echo -e "${YELLOW}Warning: No upstream branch configured.${NC}"
        echo "Setting upstream to origin/$CURRENT_BRANCH"
        git branch --set-upstream-to=origin/$CURRENT_BRANCH $CURRENT_BRANCH
        REMOTE=$(git rev-parse @{u})
    fi

    if [ "$LOCAL" = "$REMOTE" ]; then
        echo -e "${GREEN}Already up to date!${NC}"
        exit 0
    else
        # Show what will be updated
        echo -e "${BLUE}New commits available:${NC}"
        git log --oneline $LOCAL..$REMOTE
        echo ""

        read -p "Do you want to apply these updates? (y/n): " UPDATE_CHOICE

        if [ "$UPDATE_CHOICE" != "y" ] && [ "$UPDATE_CHOICE" != "Y" ]; then
            echo -e "${YELLOW}Update cancelled.${NC}"
            exit 0
        fi

        # Perform update
        echo -e "${BLUE}Pulling updates...${NC}"
        git pull origin "$CURRENT_BRANCH"
        echo -e "${GREEN}Code updated successfully!${NC}"
    fi
fi

# Update Python dependencies
echo ""
echo -e "${BLUE}Checking Python dependencies...${NC}"

if [ -f "requirements.txt" ]; then
    # Check if venv exists
    if [ -d "venv" ]; then
        echo -e "${BLUE}Updating dependencies in virtual environment...${NC}"
        source venv/bin/activate
        pip install -r requirements.txt --quiet
        deactivate
        echo -e "${GREEN}Dependencies updated!${NC}"
    else
        echo -e "${YELLOW}Virtual environment not found.${NC}"
        read -p "Install dependencies system-wide? (y/n): " INSTALL_CHOICE

        if [ "$INSTALL_CHOICE" = "y" ] || [ "$INSTALL_CHOICE" = "Y" ]; then
            pip3 install -r requirements.txt
            echo -e "${GREEN}Dependencies installed!${NC}"
        fi
    fi
fi

# Restart web interface
echo ""
echo -e "${BLUE}Restarting web interface...${NC}"

if [ -f "webinterface.pid" ]; then
    # Web interface is running
    if [ -f "web_restart.sh" ]; then
        echo -e "${BLUE}Using web_restart.sh...${NC}"
        bash web_restart.sh
        echo -e "${GREEN}Web interface restarted!${NC}"
    else
        # Manual restart
        echo -e "${YELLOW}web_restart.sh not found. Stopping current instance...${NC}"
        PID=$(cat webinterface.pid)
        kill "$PID" 2>/dev/null || true
        sleep 2

        if ps -p "$PID" > /dev/null 2>&1; then
            kill -9 "$PID" 2>/dev/null || true
        fi

        rm -f webinterface.pid

        echo -e "${BLUE}Starting web interface...${NC}"
        if [ -f "web_start.sh" ]; then
            bash web_start.sh
            echo -e "${GREEN}Web interface started!${NC}"
        else
            echo -e "${YELLOW}Please manually start the web interface:${NC}"
            echo "  cd $SCRIPT_DIR"
            echo "  source venv/bin/activate"
            echo "  nohup python3 app.py > webinterface.log 2>&1 &"
        fi
    fi
else
    echo -e "${YELLOW}Web interface is not running.${NC}"
    read -p "Do you want to start it now? (y/n): " START_CHOICE

    if [ "$START_CHOICE" = "y" ] || [ "$START_CHOICE" = "Y" ]; then
        if [ -f "web_start.sh" ]; then
            bash web_start.sh
            echo -e "${GREEN}Web interface started!${NC}"
        else
            echo -e "${YELLOW}Please manually start the web interface${NC}"
        fi
    fi
fi

echo ""
echo -e "${GREEN}======================================"
echo "Update completed successfully!"
echo "======================================${NC}"
echo ""
echo "Current version: $(git rev-parse --short HEAD 2>/dev/null || echo 'Unknown')"
echo ""
