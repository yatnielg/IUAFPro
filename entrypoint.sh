#!/usr/bin/env bash
set -e


# Espera a DB si hace falta (simple)
if [ -n "${DATABASE_URL}" ]; then
echo "Usando DATABASE_URL=${DATABASE_URL}"
fi


cd /app


# Migraciones y estáticos
python manage.py migrate --noinput
python manage.py collectstatic --noinput


# Ejecutar gunicorn (WSGI). Para ASGI, reemplaza por daphne/uvicorn
exec gunicorn miapp.wsgi:application \
--bind 0.0.0.0:8000 \
--workers 3 \
--timeout 60 \
--access-logfile - \
--error-logfile -

#Da permisos de ejecución: chmod +x entrypoint.sh    