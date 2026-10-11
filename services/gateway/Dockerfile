FROM python:3.14-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY services/gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/gateway/ .
COPY proto/ /app/proto_src/

RUN set -e; \
    mkdir -p app/proto; \
    touch app/proto/__init__.py; \
    for name in ingestion books auth user_data recommendation; do \
        python -m grpc_tools.protoc \
            -I/app/proto_src \
            --python_out=. \
            --grpc_python_out=. \
            --pyi_out=. \
            /app/proto_src/${name}.proto; \
        mv ${name}_pb2.py ${name}_pb2_grpc.py ${name}_pb2.pyi app/proto/; \
        sed -i "s/^import ${name}_pb2/from . import ${name}_pb2/g" app/proto/${name}_pb2_grpc.py; \
    done

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV TZ=Europe/Warsaw

EXPOSE 8040

CMD ["python", "-m", "app.main"]
