#!/bin/sh
set -e

# Migrations run only in the API container; the worker starts with RUN_MIGRATIONS=false.
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  python manage.py migrate --noinput
fi

exec "$@"
