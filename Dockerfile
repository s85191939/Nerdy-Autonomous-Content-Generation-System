# Nerdy web app — deploy to any container host (Render, Railway, Fly, etc.)
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Default port; override at runtime (e.g. Render sets PORT)
ENV PORT=8080

# Gunicorn with 1 worker (state is in-memory); threads for concurrency
CMD gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 4 web.app:app
