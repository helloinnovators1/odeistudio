from odei_api.services.secret_redaction import StreamingSecretRedactor, redact_secrets


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



@pytest.mark.parametrize(
    "secret",
    [
        "sk-proj-abcdefghijklmnopqrstuvwxyz123456",
        "ghp_abcdefghijklmnopqrstuvwxyz123456",
        "Bearer abcdefghijklmnopqrstuvwxyz012345",
        "api_key=super_secret_token_12345",
        "mongodb://service-user:super_secret_password@db.example.test/odei",
        "-----BEGIN PRIVATE KEY-----\\nprivate-material\\n-----END PRIVATE KEY-----",
    ],
)
def test_streaming_secret_redactor_handles_secrets_split_across_chunks(secret):
    redactor = StreamingSecretRedactor()
    chunks = [secret[:5], secret[5:17], secret[17:]]
    result = "".join(redactor.feed(chunk) for chunk in chunks) + redactor.finish()
    assert secret not in result
    assert "[REDACTED" in result or "Bearer [REDACTED]" in result


def test_streaming_secret_redactor_preserves_normal_text_and_redacts_jwt_split():
    redactor = StreamingSecretRedactor()
    first = redactor.feed("This is safe output followed by eyJabcdefghijk.abcdefghijk.")
    second = redactor.feed("abcdefghijk and then more safe text.")
    result = first + second + redactor.finish()
    assert result.startswith("This is safe output followed by ")
    assert "eyJabcdefghijk.abcdefghijk.abcdefghijk" not in result
    assert result.endswith(" and then more safe text.")



def test_streaming_redactor_handles_long_mongodb_credentials_without_redacting_hosts():
    redactor = StreamingSecretRedactor()
    prefix = "mongodb://" + "service-user" + ":" + ("p" * 240)
    first = redactor.feed("Use this URI " + prefix)
    second = redactor.feed("@db.example.test:27017/odei")
    result = first + second + redactor.finish()
    assert ("p" * 240) not in result
    assert "[REDACTED]" in result

    ordinary = StreamingSecretRedactor()
    safe = "Connect to mongodb://db.example.test:27017/odei"
    assert ordinary.feed(safe) + ordinary.finish() == safe
