#!/bin/sh

/home/pi/.local/bin/gunicorn \
    pihome:app \
    --bind 0.0.0.0:5005 \
    --worker-class eventlet \
    --workers 1 \
    --access-logfile /var/log/gunicorn.log \
    --access-logformat '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(L)s' \
    --error-logfile /var/log/gunicorn-error.log \
    --log-level INFO \
    --reload
    #--forwarded-allow-ips "*"
