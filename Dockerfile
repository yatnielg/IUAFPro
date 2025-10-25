FROM python:3.12-slim


# Variables para pip y evitar prompts
ENV PYTHONDONTWRITEBYTECODE=1 \
PYTHONUNBUFFERED=1 \
PIP_DISABLE_PIP_VERSION_CHECK=on \
PIP_NO_CACHE_DIR=on


# Paquetes del sistema (libpq para psycopg)
RUN apt-get update && apt-get install -y --no-install-recommends \
build-essential libpq-dev curl && \
rm -rf /var/lib/apt/lists/*


WORKDIR /app


# Requisitos opcionales si tienes requirements.txt en src
COPY src/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip wheel && \
pip install -r /app/requirements.txt || true


# Gunicorn + Postgres driver por si no estaban en requirements
RUN pip install gunicorn psycopg[binary]


# Copiamos el proyecto
COPY src /app


# Crear usuario no root
RUN useradd -m django && chown -R django:django /app
USER django


EXPOSE 8000


# El entrypoint hará migraciones, collectstatic y lanzará gunicorn
CMD ["entrypoint.sh"]