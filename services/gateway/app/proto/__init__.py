try:
    import app.proto.ingestion_pb2 as ingestion_pb2
    import app.proto.ingestion_pb2_grpc as ingestion_pb2_grpc

    __all__ = [
        "ingestion_pb2",
        "ingestion_pb2_grpc",
    ]
except ImportError:
    pass
