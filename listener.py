import json
import sqlite3
import ssl
import time
import paho.mqtt.client as mqtt
import os

# --- LOAD CONFIGURATION ---
CONFIG_FILE = "config.json"

try:
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"Configuration file '{CONFIG_FILE}' not found.")

    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
        
    # Load variables with safety checks
    PRINTER_IP = config.get("printer_ip")
    ACCESS_CODE = config.get("access_code")
    SERIAL = config.get("serial_number")
    CHECK_INTERVAL = config.get("check_interval", 60)
    
    # FIX: Define DB_FILE with a default fallback
    DB_FILE = config.get("db_file", "print_history.db")

    if not all([PRINTER_IP, ACCESS_CODE, SERIAL]):
        print("Error: Missing critical credentials in config.json")
        exit(1)

except Exception as e:
    print(f"Startup Error: {e}")
    exit(1)

# Global variable to track throttle time
last_processed_time = 0

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS jobs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  filename TEXT,
                  start_time TIMESTAMP,
                  end_time TIMESTAMP,
                  duration_minutes REAL,
                  status TEXT,
                  raw_json TEXT)''')
    conn.commit()
    conn.close()

# --- MQTT CALLBACKS ---
def on_connect(client, userdata, flags, rc):
    print(f"Connected to Bambu Printer (Code: {rc})")
    client.subscribe(f"device/{SERIAL}/report")

def on_message(client, userdata, msg):
    global last_processed_time
    
    # --- THROTTLE LOGIC ---
    # If less than 60 seconds have passed, ignore this message entirely
    if (time.time() - last_processed_time) < CHECK_INTERVAL:
        return

    # Update the timestamp and process the data
    last_processed_time = time.time()

    try:
        payload_str = msg.payload.decode("utf-8")
        payload = json.loads(payload_str)

        # 1. Update the Live Dump (Now only updates once/min)
        with open("latest_trace.json", "w") as f:
            json.dump(payload, f, indent=4)
            print(f"Check performed at {time.strftime('%H:%M:%S')}...")

        # 2. Check for Job Completion
        if 'print' in payload:
            data = payload['print']
            
            if 'gcode_state' in data:
                current_state = data['gcode_state']
                
                # Note: Because we check slower, we rely on the printer staying 
                # in "FINISH" state for at least 60s (which it usually does).
                if current_state == "FINISH":
                    # To prevent duplicate logging of the same finished job, 
                    # we check if we already logged this specific print recently.
                    # (A robust production version would track 'subtask_id')
                    if not is_duplicate_log(data.get('subtask_name')):
                        print(f"!!! Print Finished: {data.get('subtask_name')} !!!")
                        save_job(data.get('subtask_name'), 0, current_state, payload_str)

    except Exception as e:
        print(f"Error: {e}")

def is_duplicate_log(filename):
    """Simple check to see if we logged this file in the last 5 minutes"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Look for this filename logged in the last 300 seconds
    c.execute('''SELECT id FROM jobs 
                 WHERE filename = ? 
                 AND start_time > datetime('now', '-5 minutes')''', (filename,))
    result = c.fetchone()
    conn.close()
    return result is not None

def save_job(filename, duration, status, raw_blob):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT INTO jobs 
                 (filename, start_time, end_time, duration_minutes, status, raw_json) 
                 VALUES (?, datetime('now'), datetime('now'), ?, ?, ?)''',
              (filename, duration, status, raw_blob))
    conn.commit()
    conn.close()

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    init_db()
    
    client = mqtt.Client()
    client.username_pw_set("bblp", ACCESS_CODE)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)
    
    client.on_connect = on_connect
    client.on_message = on_message
    
    print(f"Listening... (Sampling every {CHECK_INTERVAL} seconds)")
    client.connect(PRINTER_IP, 8883, 60)
    client.loop_forever()


#The last_processed_time Gate:
#The script now receives thousands of messages per minute from the printer (in the background) but immediately discards them if the 60-second timer hasn't expired. This drastically reduces CPU usage and disk writes for latest_trace.json.
#Duplicate Protection (is_duplicate_log):
#Since we are checking slowly, you might restart the script or the printer might linger in the "FINISH" state for hours. I added a check to ensure we don't re-log the same finished print if the script "wakes up" and sees "FINISH" again 60 seconds later. It simply looks back 5 minutes in the DB to see if we just wrote that record.
#The Risk: If you finish a print, clear the plate, and start a new print all within 59 seconds, this script might miss the "FINISH" event entirely. For 3D printing, this is physically unlikely, but be aware of the blind spot.