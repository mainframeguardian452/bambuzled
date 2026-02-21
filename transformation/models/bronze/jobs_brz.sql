{{
    config(materialized='table')
}}

-- Bronze layer: completed print job history.
--
-- Selects only FINISH-state records from the raw jobs table and exposes
-- clean, typed columns for downstream analysis.  The raw_json column is
-- intentionally excluded here; additional fields will be promoted from it
-- in future iterations.

select
    job_id,
    filename,
    start_time,
    end_time,
    round(duration_minutes, 2) as duration_minutes
from {{ source('raw', 'jobs_raw') }}
where status = 'FINISH'
