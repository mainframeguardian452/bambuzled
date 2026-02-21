# Bambuzled: Bambu Lab Print History Pipeline

A containerised data pipeline that captures real-time print job events from a
Bambu Lab 3D printer and transforms them into a local medallion architecture
using dbt and Dagster.

---

## Architecture

```
Bambu Printer (MQTT over TLS)
        │
        ▼
┌──────────────────┐
│  bambu_logger    │  Container 1 – Python MQTT listener
│  (port: none)    │  Writes raw records to SQLite → Bronze / Raw layer
└────────┬─────────┘
         │ shared Docker volume (/data/print_history.db)
         ▼
┌──────────────────┐
│  bambu_dagster   │  Container 2 – Dagster webserver + daemon
│  port: 3000      │  Sensor polls DB → triggers dbt on new FINISH jobs
└────────┬─────────┘
         │ dbt run (subprocess)
         ▼
┌──────────────────┐
│  bambu_dbt_docs  │  Container 3 – dbt documentation server
│  port: 8080      │  Serves the dbt project docs / lineage graph
└──────────────────┘
```

### Medallion Layers

| Layer  | Table        | Owner           | Description                                   |
|--------|--------------|-----------------|-----------------------------------------------|
| Raw    | `jobs_raw`   | Python listener | OLTP-style; one row per job, updated in place |
| Bronze | `jobs_brz`   | dbt             | Immutable history of completed (FINISH) jobs  |

---

## Services

| Container        | URL                      | Purpose                                  |
|------------------|--------------------------|------------------------------------------|
| `bambu_logger`   | —                        | MQTT listener; no HTTP interface         |
| `bambu_dagster`  | http://localhost:3000    | Dagster UI (jobs, sensors, run history)  |
| `bambu_dbt_docs` | http://localhost:8080    | dbt docs (model lineage, column docs)    |

---

## Setup

### 1. Configure printer credentials

Edit `ingestion/config.json`:
```json
{
    "printer_ip": "192.168.x.x",
    "access_code": "your_access_code",
    "serial_number": "your_serial",
    "check_interval": 60,
    "db_file": "/data/print_history.db"
}
```

### 2. Start the stack

```bash
docker compose up --build
```

All three containers will start. The logger begins listening immediately;
Dagster and the dbt docs server are available at their respective ports within
a few seconds of startup.

### 3. Trigger a dbt run manually (optional)

From the Dagster UI at `localhost:3000`, navigate to **Jobs → transform_print_history**
and click **Materialize**. Alternatively, let the `new_print_job_sensor` fire
automatically when the next print completes.

---

## Project Layout

```
Bambuzled/
├── docker-compose.yml
├── ingestion/                  # Container 1 – MQTT listener
│   ├── listener.py             # Main service; writes raw job records
│   ├── config.json             # Printer credentials (not committed)
│   ├── requirements.txt
│   └── Dockerfile
├── orchestration/              # Container 2 – Dagster
│   ├── repo.py                 # Dagster Definitions: job + sensor
│   ├── workspace.yaml
│   ├── requirements.txt
│   └── Dockerfile
└── transformation/             # Container 3 – dbt project
    ├── dbt_project.yml
    ├── profiles.yml
    ├── requirements.txt
    ├── Dockerfile
    └── models/
        ├── sources.yml         # Declares the raw 'jobs' table as a source
        └── bronze/
            └── jobs_brz.sql            # Bronze model: completed job history
```

---

## How the Sensor Works

The `new_print_job_sensor` in Dagster polls the SQLite database every 30 seconds.
It stores a **high-water mark** (the highest `id` of a FINISH-state row seen so
far). When a new finished job appears, the sensor yields a `RunRequest` that
triggers `transform_print_history`, which shells out to `dbt run --select bronze`.
The resulting `jobs_brz` table is rebuilt from all completed jobs in
the raw layer.

---

## Notes

- **Throttling:** The listener discards MQTT messages received within 60 seconds
  of the last processed message, drastically reducing CPU and disk activity.
- **Duplicate safety:** The raw `jobs` table has a `UNIQUE` constraint on
  `job_id`, so re-delivered MQTT events are silently ignored.
- **dbt docs cold start:** On first boot, if the SQLite database does not yet
  exist, the dbt-docs container falls back to `dbt compile` (no DB required)
  so the docs UI still loads. A full catalog (column types, row counts) is
  generated once the DB is available and the container restarts.
