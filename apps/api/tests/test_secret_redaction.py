from odei_api.services.secret_redaction import redact_secrets


def test_redacts_known_provider_tokens_and_quoted_secret_assignments() -> None:
    token = "sk-proj-" + "A" * 28
    result = redact_secrets('api_key="' + token + '"\npassword="correct-horse-battery"\n')
    assert token not in result
    assert "correct-horse-battery" not in result
    assert result.count("[REDACTED]") >= 2
    unquoted = redact_secrets("DB_PASSWORD=plain-secret-value-12345")
    assert "plain-secret-value-12345" not in unquoted


def test_redacts_jwts_private_keys_and_database_passwords() -> None:
    jwt = "eyJ" + "A" * 18 + "." + "B" * 20 + "." + "C" * 20
    pem = "-----BEGIN PRIVATE KEY-----\nsecret-material\n-----END PRIVATE KEY-----"
    uri = "mongodb+srv://user:database-password@cluster.example/db"
    result = redact_secrets(jwt + "\n" + pem + "\n" + uri)
    assert jwt not in result
    assert "secret-material" not in result
    assert "database-password" not in result
    assert "[REDACTED PRIVATE KEY]" in result
