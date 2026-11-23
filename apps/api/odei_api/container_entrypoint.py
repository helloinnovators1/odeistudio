"""Container entrypoint for platform-provided HTTP port configuration."""
from __future__ import annotations

import os


def parse_port(value: str | None) -> int:
    """Return a valid TCP port, defaulting to the conventional container port."""
    raw = "8000" if value is None or not value.strip() else value.strip()
    try:
        port = int(raw)
    except ValueError as exc:
        raise ValueError("PORT must be an integer between 1 and 65535") from exc
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be an integer between 1 and 65535")
    return port


def main() -> None:
    import uvicorn

    uvicorn.run(
        "odei_api.main:app",
        host="0.0.0.0",
        port=parse_port(os.getenv("PORT")),
        proxy_headers=False,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
