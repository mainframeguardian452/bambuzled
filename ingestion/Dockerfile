FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy script and config
COPY . .

# Run unbuffered (-u) so logs appear immediately
CMD ["python", "-u", "listener.py"]