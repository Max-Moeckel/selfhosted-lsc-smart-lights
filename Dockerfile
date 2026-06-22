FROM python:3.12-slim

WORKDIR /app

# Local timezone for the wake-up scheduler: wakeup._loop matches the configured
# HH:MM against datetime.now(), which reads the OS local time. The slim image has
# no zoneinfo, so glibc would silently fall back to UTC and the alarm would fire
# 1–2 h off. Install tzdata and pin TZ so "07:00" means 07:00 local. (Overridable
# via the TZ env in docker-compose-prod.yml.)
ENV TZ=Europe/Berlin
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY lamp.py app.py wakeup.py party.py status.py ./
COPY templates/ ./templates/
COPY static/ ./static/

# config/ (device keys + wake-up settings) is NOT baked in — it is bind-mounted at
# runtime (see docker-compose.yml). Create the mount point so the path always exists.
RUN mkdir -p /app/config

EXPOSE 8080

# single worker: the wake-up scheduler and the SSE status poller run as background
# threads and must not be duplicated. Threads bumped to 8 because every open browser
# holds one /api/stream (SSE) connection for its whole lifetime, occupying a thread.
CMD ["gunicorn", "-b", "0.0.0.0:8080", "-w", "1", "--threads", "8", "--timeout", "30", "app:app"]
