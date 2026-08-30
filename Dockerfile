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
CMD gunicorn app:app --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 120
