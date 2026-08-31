# Playwright's official image ships Chromium plus every OS-level dependency
# it needs already installed — far more reliable on a hosted platform than
# hoping the build sandbox can apt-get font/codec packages itself.
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=10000
EXPOSE 10000

WORKDIR /app/storefront
# gthread (real OS threads), not gevent: gevent's worker monkey-patches the
# whole process (threading/socket/subprocess), which makes Playwright's sync
# API misdetect a running asyncio loop and refuse to launch the browser at
# all ("It looks like you are using Playwright Sync API inside the asyncio
# loop"). gthread avoids that entirely and still lets flask-sock hijack a
# WebSocket connection's socket without blocking the other threads.
# --access-logfile/--error-logfile '-' send both to stdout/stderr (Render's
# log stream) — without this, gunicorn logs no HTTP access lines at all,
# which made it impossible to tell whether a request even reached the
# server versus failing before it got here.
CMD gunicorn app:app --bind 0.0.0.0:${PORT} --worker-class gthread --workers 2 --threads 8 --timeout 120 --access-logfile - --error-logfile -
