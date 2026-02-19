# Use the same base python version as your logger for consistency
FROM python:3.9-slim

# 1. Set Environment Variables
# DAGSTER_HOME: Where Dagster stores run history and logs
ENV DAGSTER_HOME=/opt/dagster/dagster_home
ENV PYTHONPATH=/opt/dagster/app

# 2. Prepare the Directory Structure
# We create the home directory and the app directory
RUN mkdir -p $DAGSTER_HOME /opt/dagster/app

# 3. Install Dependencies
# We copy requirements first to leverage Docker layer caching
WORKDIR /opt/dagster/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy Dagster Code
# We copy the local 'my_dagster_project' code into the container
COPY . .

# 5. Setup Workspace
# Create a minimalist workspace.yaml if one wasn't copied
RUN echo "load_from: \n  - python_file: my_dagster_project/repo.py" > workspace.yaml

# 6. Create a placeholder dagster.yaml (Critical for avoiding warnings)
RUN touch $DAGSTER_HOME/dagster.yaml

# 7. Expose the UI Port
EXPOSE 3000

# 8. Start Command
# "dagster dev" runs both the Webserver (UI) and the Daemon (Scheduler/Sensors)
# -h 0.0.0.0 allows access from outside the container
CMD ["dagster", "dev", "-h", "0.0.0.0", "-p", "3000"]