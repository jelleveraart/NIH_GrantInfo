#!/bin/bash
cd "$(dirname "$0")"

# Install dependencies quietly (first run only takes a moment)
pip install -r requirements.txt --quiet

# Open the browser after a short delay, in the background
( sleep 2 && open http://127.0.0.1:5000 ) &

# Run Flask in the FOREGROUND so the window/stdout stays alive
python3 app.py