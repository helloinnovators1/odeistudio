"""Lazy PyMongo Async client construction with explicit configuration checks."""
from pymongo import AsyncMongoClient

from odei_api.config import Settings, get_settings


class MongoConfigurationError(RuntimeError):
    """Raised when MongoDB configuration is missing."""


def create_mongo_client(settings: Settings | None = None) -> tuple[AsyncMongoClient, str]:
    """Create a client without connecting; callers own its async lifecycle."""
    config = settings or get_settings()
    if config.mongodb_uri is None or not config.mongodb_uri.get_secret_value():
        raise MongoConfigurationError("MONGODB_URI is not configured")
    database_name = config.mongodb_database.strip()
    if not database_name:
        raise MongoConfigurationError("MONGODB_DATABASE must not be empty")
    client = AsyncMongoClient(config.mongodb_uri.get_secret_value(), serverSelectionTimeoutMS=3000)
    return client, database_name
