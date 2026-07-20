"""Symmetric encryption for router credentials.

Router API passwords must be readable by the provisioning worker, so they
are encrypted rather than hashed. The key lives in ROUTER_CRED_KEY, never
in the database — a database dump alone must not yield router access to
your core network.

Generate a key with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Losing the key makes every stored password unreadable. Rotating it means
re-entering every router credential.
"""

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class CredentialError(Exception):
    """Raised when a stored credential cannot be decrypted."""


def _fernet():
    key = getattr(settings, 'ROUTER_CRED_KEY', '')
    if not key:
        raise ImproperlyConfigured(
            'ROUTER_CRED_KEY is not set. Router credentials cannot be stored '
            'or read without it. Generate one with: python -c "from '
            'cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured(f'ROUTER_CRED_KEY is not a valid Fernet key: {exc}')


def encrypt(plaintext: str) -> bytes:
    if plaintext is None:
        return b''
    return _fernet().encrypt(plaintext.encode())


def decrypt(token: bytes) -> str:
    if not token:
        return ''
    try:
        return _fernet().decrypt(bytes(token)).decode()
    except InvalidToken as exc:
        # Almost always a rotated or mismatched key. Say so, rather than
        # letting a confusing InvalidToken surface from a provisioning task.
        raise CredentialError(
            'Stored credential could not be decrypted. ROUTER_CRED_KEY has '
            'most likely changed since it was saved.'
        ) from exc
