#!/bin/bash
# The API and the data worker run side by side so they share one volume (DATA_DIR): the worker
# writes the forecast copy and zone outlines there, the API reads them. If the worker ever exits,
# it is started again; the API keeps serving meanwhile, falling back to the network providers.
(
  while true; do
    python manage.py worker
    echo "data worker exited ($?); restarting in 30 s" >&2
    sleep 30
  done
) &
exec uvicorn config.asgi:application --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips '*'
