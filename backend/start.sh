#!/bin/sh
# The API and the data worker run side by side so they share one volume (DATA_DIR): the worker
# writes the forecast copy and zone outlines there, the API reads them. Railway sets PORT.
python manage.py worker &
exec uvicorn config.asgi:application --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips '*'
