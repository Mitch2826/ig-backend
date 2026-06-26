# Dockerfile
# Production image for the I&G Flask backend.
# Used by Render (and later AWS EC2/ECS) to build and run the app.
#
# Build locally to test:
#   docker build -t iandg-backend .
#   docker run -p 5000:5000 --env-file .env iandg-backend

FROM python:3.11-slim

WORKDIR /app

# System dependencies needed by psycopg2 (PostgreSQL driver)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (separate layer — only rebuilds when
# requirements.txt changes, not on every code change, speeding up rebuilds)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Render (and most platforms) inject PORT via environment variable —
# gunicorn binds to it dynamically at container start, not hardcoded here
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

# Gunicorn is the production WSGI server — Flask's built-in dev server
# (used by run.py locally) is explicitly unsafe for production per
# Flask's own warning message we've seen in the terminal output.
#
# --workers 2: reasonable for Render's free tier resource limits
# --timeout 120: Daraja/iPay calls can take a few seconds; default 30s
#                timeout could kill a request mid-payment-initiation
CMD gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 --timeout 120 "app:create_app()"