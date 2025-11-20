#!/bin/bash

# GameServer Web Interface - Start Script
# Starts the web interface in the background using nohup

cd "$(dirname "$0")"

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
