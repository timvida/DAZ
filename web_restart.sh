#!/bin/bash

# GameServer Web Interface - Restart Script
# Stops and restarts the web interface

cd "$(dirname "$0")"

echo "Restarting web interface..."
echo ""

# Stop if running
if [ -f "webinterface.pid" ]; then
    ./web_stop.sh
    echo ""
    sleep 2
fi

# Start
./web_start.sh
