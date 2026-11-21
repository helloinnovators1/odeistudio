from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated server configuration; secrets are never exposed by API routes."""

    app_name: str = "ODEI Studio API"
    app_version: str = "0.1.0"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None
    mongodb_uri: SecretStr | None = None
    mongodb_database: str = "odei_studio"
    auth_issuer: str | None = None
    auth_audience: str | None = None
    auth_jwks_url: str | None = None
    auth_allowed_client_ids: str | None = None
    cors_allowed_origins: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def parse_cors_origins(value: str) -> list[str]:
    """Parse explicit browser origins; reject wildcard, paths, credentials and insecure hosts."""
    origins: list[str] = []
    for raw in value.split(","):
        origin = raw.strip()
        if not origin:
            continue
        try:
            parsed = urlsplit(origin)
            hostname = parsed.hostname
            # Accessing .port also validates malformed port syntax.
            port = parsed.port
        except ValueError as exc:
            raise ValueError("CORS_ALLOWED_ORIGINS contains an invalid origin") from exc
        loopback = hostname in {"localhost", "127.0.0.1", "::1"}
        if (
            parsed.scheme not in ({"https", "http"} if loopback else {"https"})
            or not parsed.netloc
            or not hostname
            or (port is not None and not 1 <= port <= 65535)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or origin == "*"
        ):
            raise ValueError("CORS_ALLOWED_ORIGINS must contain explicit HTTPS origins (HTTP only for loopback)")
        normalized = f"{parsed.scheme}://{parsed.netloc}"
        if normalized not in origins:
            origins.append(normalized)
    return origins
