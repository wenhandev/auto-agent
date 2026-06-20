#!/bin/sh
set -eu

mkdir -p /app/data

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips="*"
