import pytest

from odei_api.container_entrypoint import parse_port


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 8000),
        ("", 8000),
        ("  ", 8000),
        ("8000", 8000),
        ("10000", 10000),
        ("65535", 65535),
        ("1", 1),
    ],
)
def test_parse_port_accepts_valid_platform_ports(value, expected):
    assert parse_port(value) == expected


@pytest.mark.parametrize("value", ["0", "-1", "65536", "abc", "80.5", "1,2"])
def test_parse_port_rejects_invalid_platform_ports(value):
    with pytest.raises(ValueError, match="PORT must be an integer"):
        parse_port(value)


def test_main_uses_platform_port_without_trusting_forwarded_headers(monkeypatch):
    import uvicorn

    from odei_api.container_entrypoint import main

    captured = {}
    monkeypatch.setenv("PORT", "10000")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda app, **kwargs: captured.update(app=app, **kwargs),
    )

    main()

    assert captured["app"] == "odei_api.main:app"
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 10000
    assert captured["proxy_headers"] is False
    assert captured["log_level"] == "debug"
