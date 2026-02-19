# Bambuzled:  Bambu Lab MQTT Logger

A lightweight Python service that listens to Bambu Lab 3D printers via MQTT and logs job history to a local SQLite database.

## Features
- **Real-time Listening:** Captures "FINISH" states from the printer.
- **Raw Data Capture:** Stores the full JSON payload for debugging.
- **Throttling:** Configurable sampling rate (Default: 60s) to reduce noise.

## Setup

1. **Install Dependencies**
   ```bash
   py -m venv venv
   pip install -r requirements.txt


## Notes
   - **The last_processed_time Gate:**  The script now receives thousands of messages per minute from the printer (in the background) but immediately discards them if the 60-second timer hasn't expired. This drastically reduces CPU usage and disk writes for latest_trace.json.
