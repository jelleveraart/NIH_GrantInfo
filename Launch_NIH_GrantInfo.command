#!/bin/bash
cd "$(dirname "$0")"

echo "Setting up NIH Grant Info..."

# Use the SAME python that will run the app to install dependencies.
# 'python3 -m pip' guarantees pip and the interpreter match.
python3 -m pip install --user -r requirements.txt

echo "Starting the app..."

# Open the browser after a short delay, in the background
( sleep 3 && open http://127.0.0.1:5000 ) &

# Run Flask in the foreground so the window/stdout stays alive
python3 app.py