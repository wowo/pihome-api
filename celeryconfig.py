#!/usr/bin/python

CELERY_RESULT_SERIALIZER='json'

BROKER_URL='redis://localhost:6379/0'
RESULT_BACKEND = 'redis://localhost:6379/0'
