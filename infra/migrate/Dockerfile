FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN pip install --no-cache-dir "pymssql==2.3.4" "psycopg[binary]==3.2.9"
COPY tables.py migrate.py roles.sql ./
CMD ["python", "-u", "migrate.py"]
