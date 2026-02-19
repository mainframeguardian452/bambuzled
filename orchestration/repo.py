import sqlite3
from dagster import sensor, RunRequest, repository, define_asset_job, AssetSelection
from dagster_dbt import dbt_assets, DbtCliResource

# --- CONFIGURATION ---
DB_PATH = "/path/to/print_history.db"  # Path to the shared volume

# --- 1. DEFINE THE DBT JOB ---
# This assumes you have defined your dbt assets (standard Dagster+dbt setup)
# For this snippet, we create a generic job that runs all dbt models.
run_dbt_job = define_asset_job(
    name="transform_print_history",
    selection=AssetSelection.all()
)

# --- 2. DEFINE THE SENSOR ---
@sensor(job=run_dbt_job)
def new_print_job_sensor(context):
    """
    Polls the SQLite DB. Triggers a run if the highest Job ID increases.
    """
    try:
        # Connect to the raw database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get the ID of the most recent finished job
        cursor.execute("SELECT MAX(id) FROM jobs WHERE status = 'FINISH'")
        result = cursor.fetchone()
        current_max_id = result[0] if result and result[0] else 0
        
        conn.close()
        
        # Get the previous ID we processed (stored in Dagster's state)
        # The cursor is stored as a string, so we cast it.
        previous_max_id = int(context.cursor) if context.cursor else -1

        # --- LOGIC: DID DATA CHANGE? ---
        if current_max_id > previous_max_id:
            yield RunRequest(
                run_key=str(current_max_id), # Unique key prevents duplicate runs
                run_config={} 
            )
            # Update the cursor to the new High Water Mark
            context.update_cursor(str(current_max_id))
            context.log.info(f"New Print Job Detected! (ID: {current_max_id})")
            
    except Exception as e:
        context.log.error(f"Sensor failed to read DB: {e}")

# --- 3. REGISTER THE REPO ---
@repository
def bambu_data_repo():
    return [run_dbt_job, new_print_job_sensor]