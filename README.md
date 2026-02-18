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