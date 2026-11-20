"""Lazy PyMongo Async client construction with explicit configuration checks."""
from pymongo import AsyncMongoClient

from odei_api.config import get_settings


class MongoConfigurationError(RuntimeError):
    """Raised when MongoDB configuration is missing."""


def create_mongo_client() -> tuple[AsyncMongoClient, str]:
    settings = get_settings()
    if settings.mongodb_uri is None or not settings.mongodb_uri.get_secret_value():
        raise MongoConfigurationError("MONGODB_URI is not configured")
    database_name = settings.mongodb_database.strip()
    if not database_name:
        raise MongoConfigurationError("MONGODB_DATABASE must not be empty")
    client = AsyncMongoClient(settings.mongodb_uri.get_secret_value())
    return client, database_name
