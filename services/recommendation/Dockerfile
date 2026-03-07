FROM python:3.14-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY services/recommendation/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/recommendation/ .
COPY proto/ /app/proto_src/

RUN mkdir -p app/proto && \
    touch app/proto/__init__.py && \
    python -m grpc_tools.protoc \
    -I/app/proto_src \
    --python_out=. \
    --grpc_python_out=. \
    --pyi_out=. \
    /app/proto_src/recommendation.proto && \
    mv recommendation_pb2.py app/proto/ && \
    mv recommendation_pb2_grpc.py app/proto/ && \
    mv recommendation_pb2.pyi app/proto/ && \
    sed -i 's/^import recommendation_pb2/from . import recommendation_pb2/g' app/proto/recommendation_pb2_grpc.py

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV TZ=Europe/Warsaw

EXPOSE 50056

CMD ["python", "-m", "app.main"]
