#!/bin/bash

# Activate the virtual environment
source gtm_venv/bin/activate

# Kill any existing flask processes
pkill -f "python server.py" || true

# Start the Flask application in production mode
python server.py > flask.log 2>&1 &

# Display process information
echo "Flask server started with GTM server-side tracking on 127.0.0.1:5015"
echo "Process ID: $!"
echo "View logs in flask.log"
