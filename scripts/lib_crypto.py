"""AES-GCM encryption of dashboard payload.

Uses PBKDF2-HMAC-SHA256 (200k iterations) to derive a 256-bit key from the
user's password, then AES-GCM to encrypt the JSON payload. The browser uses
SubtleCrypto (native) to decrypt with the same parameters.
"""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

PBKDF2_ITERATIONS = 200_000


def encrypt_payload(text: str, password: str) -> dict:
    """Encrypt a plaintext string with a password. Returns a dict that can be
    JSON-serialized. The browser decrypts using window.crypto.subtle."""
    salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    key = kdf.derive(password.encode("utf-8"))
    iv = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, text.encode("utf-8"), None)
    return {
        "encrypted": True,
        "v": 1,
        "kdf": "PBKDF2-HMAC-SHA256",
        "iter": PBKDF2_ITERATIONS,
        "alg": "AES-GCM",
        "salt": base64.b64encode(salt).decode("ascii"),
        "iv": base64.b64encode(iv).decode("ascii"),
        "ct": base64.b64encode(ciphertext).decode("ascii"),
    }
