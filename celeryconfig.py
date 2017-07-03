#!/usr/bin/python

CELERY_RESULT_SERIALIZER='json'

BROKER_URL='redis://127.0.0.1:6379/0'
RESULT_BACKEND = 'redis://127.0.0.1:6379/0'
