from pydantic import SecretStr
import pytest

from odei_api.config import Settings
from odei_api.mongo_client import MongoConfigurationError, create_mongo_client


def test_mongo_client_requires_uri() -> None:
    settings = Settings(mongodb_uri=None)
    with pytest.raises(MongoConfigurationError, match="MONGODB_URI"):
        create_mongo_client(settings)


def test_mongo_client_requires_database_name() -> None:
    settings = Settings(
        mongodb_uri=SecretStr("mongodb://example.invalid/"),
        mongodb_database="   ",
    )
    with pytest.raises(MongoConfigurationError, match="MONGODB_DATABASE"):
        create_mongo_client(settings)


def test_mongo_client_is_created_without_connecting(monkeypatch) -> None:
    settings = Settings(
        mongodb_uri=SecretStr("mongodb://localhost:27017/"),
        mongodb_database="odei_test",
    )
    captured = {}

    class FakeClient:
        pass

    def fake_client(uri, **kwargs):
        captured["uri"] = uri
        captured["kwargs"] = kwargs
        return FakeClient()

    monkeypatch.setattr("odei_api.mongo_client.AsyncMongoClient", fake_client)
    client, database_name = create_mongo_client(settings)

    assert isinstance(client, FakeClient)
    assert database_name == "odei_test"
    assert captured["uri"] == "mongodb://localhost:27017/"
    assert captured["kwargs"]["serverSelectionTimeoutMS"] == 3000
