FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY lamp.py app.py wakeup.py party.py ./
COPY templates/ ./templates/
COPY static/ ./static/

EXPOSE 8080

# single worker: the wake-up scheduler runs as a background thread and must not be duplicated
CMD ["gunicorn", "-b", "0.0.0.0:8080", "-w", "1", "--threads", "4", "--timeout", "30", "app:app"]
