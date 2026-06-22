FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY lamp.py app.py wakeup.py party.py status.py ./
COPY templates/ ./templates/
COPY static/ ./static/

EXPOSE 8080

# single worker: the wake-up scheduler and the SSE status poller run as background
# threads and must not be duplicated. Threads bumped to 8 because every open browser
# holds one /api/stream (SSE) connection for its whole lifetime, occupying a thread.
CMD ["gunicorn", "-b", "0.0.0.0:8080", "-w", "1", "--threads", "8", "--timeout", "30", "app:app"]
