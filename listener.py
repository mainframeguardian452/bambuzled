import json
import sqlite3
import ssl
import time
import sys
import os
import logging
from datetime import datetime
import paho.mqtt.client as mqtt

# --- LOGGING CONFIGURATION ---
# Formatted for container logs (Timestamp - Level - Message)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
CONFIG_FILE = "config.json"

try:
    if not os.path.exists(CONFIG_FILE):
        logger.critical(f"Config file '{CONFIG_FILE}' not found.")
        sys.exit(1)

    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
        
    PRINTER_IP = config.get("printer_ip")
    ACCESS_CODE = config.get("access_code")
    SERIAL = config.get("serial_number")
    CHECK_INTERVAL = config.get("check_interval", 60)
    DB_FILE = config.get("db_file", "print_history.db")

    if not all([PRINTER_IP, ACCESS_CODE, SERIAL]):
        logger.critical("Missing credentials in config.json")
        sys.exit(1)

except Exception as e:
    logger.critical(f"Startup Error: {e}")
    sys.exit(1)

last_processed_time = 0

# --- DATABASE SETUP ---
def init_db():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS jobs
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      job_id TEXT UNIQUE, 
                      filename TEXT,
                      start_time TIMESTAMP,
                      end_time TIMESTAMP,
                      duration_minutes REAL,
                      status TEXT,
                      raw_json TEXT)''')
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_job_id ON jobs(job_id)")
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Database Initialization Failed: {e}")
        sys.exit(1)

# --- ID GENERATION ---
def get_stable_job_id(data):
    filename = data.get('subtask_name', 'Unknown')
    task_id = data.get('task_id')
    
    # 1. Cloud ID
    if task_id and str(task_id) not in ["-1", "0"]:
        return str(task_id)

    # 2. Local Timestamp Fallback
    start_ts = data.get('gcode_start_time')
    if start_ts:
        clean_ts = str(int(float(start_ts)))
        return f"{filename}_{clean_ts}"
    
    # 3. Unsafe Fallback
    return f"unknown_{filename}"

# --- EVENT HANDLERS ---
def handle_print_start(data, raw_blob):
    job_id = get_stable_job_id(data)
    filename = data.get('subtask_name', 'Unknown')
    
    try:
        ts = float(data.get('gcode_start_time', time.time()))
        start_dt = datetime.fromtimestamp(int(ts))
    except:
        start_dt = datetime.now()

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        # Try to insert. If it exists, this will fail silently via IntegrityError
        c.execute('''INSERT INTO jobs 
                     (job_id, filename, start_time, status, raw_json) 
                     VALUES (?, ?, ?, ?, ?)''',
                  (job_id, filename, start_dt, "RUNNING", raw_blob))
        conn.commit()
        logger.info(f"PRINT STARTED: {filename} (ID: {job_id})")
        
    except sqlite3.IntegrityError:
        # Duplicate detected - Job is already tracked. Do nothing.
        pass 
    except Exception as e:
        logger.error(f"DB Error on Start: {e}")
    finally:
        conn.close()

def handle_print_finish(data, raw_blob):
    job_id = get_stable_job_id(data)
    filename = data.get('subtask_name', 'Unknown')
    end_dt = datetime.now()
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    try:
        c.execute("SELECT start_time, status FROM jobs WHERE job_id = ?", (job_id,))
        row = c.fetchone()
        
        if row:
            # Update existing running job
            if row[1] == "FINISH":
                 return # Already done

            start_dt = datetime.fromisoformat(row[0])
            duration = (end_dt - start_dt).total_seconds() / 60.0
            
            c.execute('''UPDATE jobs SET 
                         end_time = ?, 
                         status = 'FINISH', 
                         duration_minutes = ?, 
                         raw_json = ? 
                         WHERE job_id = ?''',
                      (end_dt, duration, raw_blob, job_id))
            conn.commit()
            logger.info(f"PRINT FINISHED: {filename} ({duration:.1f} min)")

        else:
            # Log orphan finish
            c.execute('''INSERT INTO jobs 
                         (job_id, filename, start_time, end_time, status, raw_json) 
                         VALUES (?, ?, datetime('now'), datetime('now'), 'FINISH', ?)''',
                      (job_id, filename, raw_blob))
            conn.commit()
            logger.warning(f"ORPHAN FINISHED: {filename} (Start event was missed)")
            
    except Exception as e:
        logger.error(f"DB Error on Finish: {e}")
    finally:
        conn.close()

# --- MQTT CALLBACKS ---
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info(f"Connected to Printer at {PRINTER_IP}")
        client.subscribe(f"device/{SERIAL}/report")
    else:
        logger.error(f"Connection Failed with Code {rc}")

def on_message(client, userdata, msg):
    global last_processed_time
    
    # Silent Throttle
    if (time.time() - last_processed_time) < CHECK_INTERVAL:
        return
    last_processed_time = time.time()

    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        
        # Silent Dump (Useful for debugging if you exec into container)
        with open("latest_trace.json", "w") as f:
            json.dump(payload, f, indent=4)

        if 'print' in payload:
            data = payload['print']
            state = data.get('gcode_state', 'UNKNOWN')
            
            if state == "RUNNING":
                handle_print_start(data, msg.payload.decode("utf-8"))
            elif state == "FINISH":
                handle_print_finish(data, msg.payload.decode("utf-8"))

    except Exception as e:
        logger.error(f"Payload Parsing Error: {e}")

# --- MAIN ---
if __name__ == "__main__":
    init_db()
    
    # Create Client
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    
    # Auth & SSL
    client.username_pw_set("bblp", ACCESS_CODE)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)
    
    logger.info("Starting Bambu Logger Service...")
    
    try:
        client.connect(PRINTER_IP, 8883, 60)
        client.loop_forever()
    except Exception as e:
        logger.critical(f"Fatal Network Error: {e}")
        sys.exit(1)