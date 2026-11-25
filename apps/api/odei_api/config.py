import json
import re
from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
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
    execution_profiles_json: str = ""
    execution_runtime_path: str | None = None
    execution_workspace_root: str | None = None
    execution_worker_id: str | None = None
    mad_metrics_token: SecretStr | None = None
    mac_platform_operators_json: str = Field(default="", max_length=262_144)
    mac_provider_factory_allowlist_json: str = Field(default="", max_length=8_192)
    mac_secret_resolver_factory_allowlist_json: str = Field(default="", max_length=8_192)
    auth_issuer: str | None = None
    auth_audience: str | None = None
    auth_jwks_url: str | None = None
    auth_allowed_client_ids: str | None = None
    cors_allowed_origins: str = ""
    patch_approval_issuer: str | None = None
    patch_approval_key_id: str | None = None
    patch_approval_private_key_b64: SecretStr | None = None
    patch_approval_ttl_seconds: int = Field(default=60, ge=30, le=300)
    github_app_id: int | None = Field(default=None, ge=1)
    github_app_private_key_b64: SecretStr | None = None
    nexus_mcp_servers_json: str = Field(default="", max_length=65_536)

    @model_validator(mode="after")
    def validate_configuration(self):
        patch_configured = (
            self.patch_approval_issuer is not None,
            self.patch_approval_key_id is not None,
            self.patch_approval_private_key_b64 is not None,
        )
        if any(patch_configured) and not all(patch_configured):
            raise ValueError(
                "PATCH_APPROVAL_ISSUER, PATCH_APPROVAL_KEY_ID and "
                "PATCH_APPROVAL_PRIVATE_KEY_B64 must be configured together"
            )
        if self.patch_approval_issuer is not None:
            parsed = urlsplit(self.patch_approval_issuer)
            if (
                parsed.scheme != "https" or not parsed.netloc
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in {"", "/"}
            ):
                raise ValueError("PATCH_APPROVAL_ISSUER must be an exact HTTPS origin")
        github_configured = (
            self.github_app_id is not None,
            self.github_app_private_key_b64 is not None,
        )
        if any(github_configured) and not all(github_configured):
            raise ValueError("GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY_B64 must be configured together")
        if self.github_app_private_key_b64 is not None:
            import base64
            try:
                key = base64.b64decode(
                    self.github_app_private_key_b64.get_secret_value(), validate=True,
                )
            except (ValueError, TypeError) as exc:
                raise ValueError("GITHUB_APP_PRIVATE_KEY_B64 must be valid base64") from exc
            if b"-----BEGIN" not in key or b"PRIVATE KEY-----" not in key:
                raise ValueError("GITHUB_APP_PRIVATE_KEY_B64 must contain a PEM private key")
        if self.mac_platform_operators_json.strip():
            from odei_api.security.mac_rbac import parse_mac_operator_registry
            parse_mac_operator_registry(self.mac_platform_operators_json)
        factory_reference = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$")
        for setting_name, raw in (
            ("MAC_PROVIDER_FACTORY_ALLOWLIST_JSON", self.mac_provider_factory_allowlist_json),
            ("MAC_SECRET_RESOLVER_FACTORY_ALLOWLIST_JSON", self.mac_secret_resolver_factory_allowlist_json),
        ):
            if not raw.strip():
                continue
            try:
                allowed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{setting_name} must be a JSON array") from exc
            if (
                not isinstance(allowed, list) or not 1 <= len(allowed) <= 32
                or any(not isinstance(item, str) or not factory_reference.fullmatch(item) for item in allowed)
                or len(set(allowed)) != len(allowed)
            ):
                raise ValueError(f"{setting_name} must contain 1 to 32 unique module:callable references")
        if self.mad_metrics_token is not None and (
            not self.mad_metrics_token.get_secret_value().isascii()
            or len(self.mad_metrics_token.get_secret_value()) < 32
        ):
            raise ValueError("MAD_METRICS_TOKEN must contain at least 32 ASCII characters")
        from odei_api.services.mcp_gateway import load_mcp_servers
        try:
            load_mcp_servers(self.nexus_mcp_servers_json)
        except ValueError as exc:
            raise ValueError("NEXUS_MCP_SERVERS_JSON is invalid") from exc
        if self.patch_approval_key_id is not None and (
            not self.patch_approval_key_id.isascii()
            or not self.patch_approval_key_id
            or len(self.patch_approval_key_id) > 64
        ):
            raise ValueError("PATCH_APPROVAL_KEY_ID must be 1 to 64 ASCII characters")
        return self

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
            port = parsed.port
        except ValueError as exc:
            raise ValueError("CORS_ALLOWED_ORIGINS contains an invalid origin") from exc
        loopback = hostname in {"localhost", "127.0.0.1", "::1"}
        if (
            parsed.scheme not in ({"https", "http"} if loopback else {"https"})
            or not parsed.netloc or not hostname
            or (port is not None and not 1 <= port <= 65535)
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment or origin == "*"
        ):
            raise ValueError("CORS_ALLOWED_ORIGINS must contain explicit HTTPS origins (HTTP only for loopback)")
        normalized = f"{parsed.scheme}://{parsed.netloc}"
        if normalized not in origins:
            origins.append(normalized)
    return origins
