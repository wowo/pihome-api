#!/bin/sh

/home/pi/.local/bin/gunicorn \
    pihome:app \
    --bind 0.0.0.0:5005 \
    --worker-class eventlet \
    --workers 1 \
    --access-logfile /var/log/gunicorn.log \
    --log-level INFO \
    --reload \
    --forwarded-allow-ips "*"
