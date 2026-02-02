FROM python:3.14-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY services/gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/gateway/ .
COPY proto/ /app/proto_src/

RUN mkdir -p app/proto && \
    touch app/proto/__init__.py && \
    python -m grpc_tools.protoc \
    -I/app/proto_src \
    --python_out=. \
    --grpc_python_out=. \
    --pyi_out=. \
    /app/proto_src/ingestion.proto && \
    mv ingestion_pb2.py app/proto/ && \
    mv ingestion_pb2_grpc.py app/proto/ && \
    mv ingestion_pb2.pyi app/proto/ && \
    sed -i 's/^import ingestion_pb2/from . import ingestion_pb2/g' app/proto/ingestion_pb2_grpc.py

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8040

CMD ["python", "-m", "app.main"]
