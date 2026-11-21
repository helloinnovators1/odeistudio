import pytest

from odei_api.config import parse_cors_origins


def test_parse_cors_origins_accepts_explicit_https_and_loopback_http():
    assert parse_cors_origins(
        "https://studio.example.test, http://localhost:3002, http://127.0.0.1:3002"
    ) == [
        "https://studio.example.test",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
    ]


def test_parse_cors_origins_deduplicates_and_ignores_empty_entries():
    assert parse_cors_origins("https://studio.example.test/, ,https://studio.example.test") == [
        "https://studio.example.test"
    ]


@pytest.mark.parametrize(
    "value",
    [
        "*",
        "http://studio.example.test",
        "https://studio.example.test/path",
        "https://user:pass@studio.example.test",
        "https://studio.example.test?x=1",
        "https://studio.example.test#fragment",
        "not-a-url",
    ],
)
def test_parse_cors_origins_rejects_unsafe_or_malformed_origins(value):
    with pytest.raises(ValueError):
        parse_cors_origins(value)
