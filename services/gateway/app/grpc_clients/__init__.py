from app.grpc_clients.ingestion import IngestionClient, ingestion_client
from app.grpc_clients.books import BooksClient, books_client
from app.grpc_clients.auth import AuthClient, auth_client

__all__ = [
    "IngestionClient",
    "ingestion_client",
    "BooksClient",
    "books_client",
    "AuthClient",
    "auth_client",
]
