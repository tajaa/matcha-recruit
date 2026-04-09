import pytest

from app.core.services.secret_crypto import (
    SECRET_PREFIX,
    decrypt_secret,
    encrypt_secret,
    is_encrypted_secret,
)


def test_encrypt_decrypt_round_trip():
    seed = "unit-test-seed"
    encrypted = encrypt_secret("my-google-token", seed=seed)

    assert encrypted is not None
    assert encrypted.startswith(SECRET_PREFIX)
    assert is_encrypted_secret(encrypted)
    assert decrypt_secret(encrypted, seed=seed) == "my-google-token"


def test_decrypt_plaintext_passthrough():
    assert decrypt_secret("already-plain", seed="unit-test-seed") == "already-plain"


def test_encrypt_idempotent_for_already_encrypted_value():
    seed = "unit-test-seed"
    encrypted = encrypt_secret("my-google-token", seed=seed)
    reencrypted = encrypt_secret(encrypted, seed=seed)
    assert reencrypted == encrypted


def test_decrypt_invalid_encrypted_value_raises():
    with pytest.raises(ValueError, match="Unable to decrypt stored secret"):
        decrypt_secret(f"{SECRET_PREFIX}definitely-not-valid", seed="unit-test-seed")
