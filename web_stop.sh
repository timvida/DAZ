#!/bin/bash

# GameServer Web Interface - Stop Script
# Stops the running web interface

cd "$(dirname "$0")"

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
