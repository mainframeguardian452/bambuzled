import subprocess
import sqlite3
from dagster import Definitions, sensor, RunRequest, job, op

# --- CONFIGURATION ---
DB_PATH = "/data/print_history.db"
DBT_PROJECT_DIR = "/opt/dbt_project"
DBT_PROFILES_DIR = "/opt/dbt_project"


@op
def run_dbt_bronze(context):
    """Runs dbt to materialize the bronze layer from the raw jobs table."""
    result = subprocess.run(
        [
            "dbt", "run",
            "--project-dir", DBT_PROJECT_DIR,
            "--profiles-dir", DBT_PROFILES_DIR,
            "--select", "bronze",
        ],
        capture_output=True,
        text=True,
    )
    context.log.info(result.stdout)
    if result.returncode != 0:
        context.log.error(result.stderr)
        raise Exception("dbt run failed")


@job
def transform_print_history():
    run_dbt_bronze()


@sensor(job=transform_print_history, minimum_interval_seconds=30)
def new_print_job_sensor(context):
    """
    Polls the SQLite DB every 30 seconds.
    Triggers a dbt run when the highest finished job ID increases.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(id) FROM jobs_raw WHERE status = 'FINISH'")
        result = cursor.fetchone()
        current_max_id = result[0] if result and result[0] else 0
        conn.close()
    except Exception as e:
        context.log.error(f"Sensor DB error: {e}")
        return

    previous_max_id = int(context.cursor) if context.cursor else -1

    if current_max_id > previous_max_id:
        context.update_cursor(str(current_max_id))
        context.log.info(
            f"New finished print job detected (ID: {current_max_id}). Triggering dbt."
        )
        yield RunRequest(run_key=str(current_max_id))


defs = Definitions(
    jobs=[transform_print_history],
    sensors=[new_print_job_sensor],
)
