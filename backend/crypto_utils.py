"""Symmetric encryption for secrets we must store at rest (job board API keys,
OAuth client secrets, webhook signing secrets, ...) but never want sitting in
MongoDB in plaintext. Uses Fernet (AES-128-CBC + HMAC) from the `cryptography`
package, keyed by CREDENTIALS_ENCRYPTION_KEY (backend/.env, one key per
deployment — never hardcoded, never sent to the frontend).
"""
import os

from cryptography.fernet import Fernet, InvalidToken

_key = os.environ['CREDENTIALS_ENCRYPTION_KEY']
_fernet = Fernet(_key.encode() if isinstance(_key, str) else _key)


def encrypt_str(value):
    if value is None or value == '':
        return None
    return _fernet.encrypt(str(value).encode()).decode()


def decrypt_str(token):
    if not token:
        return None
    try:
        return _fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        return None


def encrypt_dict(d: dict) -> dict:
    """Encrypt every value in a flat {field_key: plaintext} dict of credentials."""
    return {k: encrypt_str(v) for k, v in (d or {}).items() if v is not None and v != ''}


def decrypt_dict(d: dict) -> dict:
    """Inverse of encrypt_dict — used server-side only, NEVER returned to the frontend."""
    return {k: decrypt_str(v) for k, v in (d or {}).items()}
