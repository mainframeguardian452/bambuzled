# Bambu Lab MQTT Logger

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
   - **Duplicate Protection (is_duplicate_log):** Since we are checking slowly, you might restart the script or the printer might linger in the "FINISH" state for hours. I added a check to ensure we don't re-log the same finished print if the script "wakes up" and sees "FINISH" again 60 seconds later. It simply looks back 5 minutes in the DB to see if we just wrote that record.
   - **The Risk:** If you finish a print, clear the plate, and start a new print all within 59 seconds, this script might miss the "FINISH" event entirely. For 3D printing, this is physically unlikely, but be aware of the blind spot.