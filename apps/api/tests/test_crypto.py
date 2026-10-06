import pytest
from cryptography.fernet import Fernet

from app.core import crypto
from app.core.crypto import CryptoError


def test_encrypt_decrypt_roundtrip():
    secret = "sk-very-secret-key-ab12"
    ciphertext = crypto.encrypt_secret(secret)
    assert ciphertext != secret.encode()
    assert crypto.decrypt_secret(ciphertext) == secret


def test_last_four():
    assert crypto.last_four("abcdef12") == "ef12"
    assert crypto.last_four("ab") == "ab"


def test_wrong_key_cannot_decrypt():
    other = Fernet(Fernet.generate_key())
    ciphertext = crypto.encrypt_secret("sk-abc")
    with pytest.raises(CryptoError):
        crypto.decrypt_secret(ciphertext, fernet=other)


def test_key_required_outside_testing(monkeypatch):
    monkeypatch.setattr(crypto.settings, "testing", False)
    monkeypatch.setattr(crypto.settings, "secret_encryption_key", None)
    with pytest.raises(CryptoError):
        crypto.get_fernet()