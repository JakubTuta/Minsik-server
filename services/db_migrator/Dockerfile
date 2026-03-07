FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY services/db_migrator/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY services/db_migrator/run_migrations.py /app/run_migrations.py
COPY services/db_migrator/alembic /app/alembic

WORKDIR /app

ENV TZ=Europe/Warsaw

CMD ["python", "run_migrations.py"]
