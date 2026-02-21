FROM python:3.9-slim

WORKDIR /opt/dbt_project

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8080

# Try full doc generation (requires live DB on shared volume).
# Fall back to compile-only (produces manifest.json without a DB connection)
# so the docs UI is always available even on a cold start.
CMD ["bash", "-c", \
     "dbt docs generate --profiles-dir . --project-dir . \
      || dbt compile --profiles-dir . --project-dir .; \
      exec dbt docs serve --profiles-dir . --project-dir . --host 0.0.0.0 --port 8080 --no-browser"]
