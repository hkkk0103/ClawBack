#!/bin/bash

# ShillTracer Backend Startup Script

echo "=================================="
echo "🦞 龙虾侦探 Backend Server"
echo "=================================="

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

# Start Flask server
echo ""
echo "Starting API server on http://localhost:5001"
echo "Press Ctrl+C to stop"
echo ""

python api.py
