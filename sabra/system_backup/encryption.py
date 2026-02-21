"""
Encryption utilities for System Backup.

Uses AES-256-GCM with PBKDF2 key derivation for secure, portable backups.
This allows backups to be restored on any server regardless of the server's
FERNET_KEYS configuration.
"""

import os
import json
import base64
import hashlib
from typing import Tuple, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend


# Constants
SALT_SIZE = 32  # 256 bits
NONCE_SIZE = 12  # 96 bits for AES-GCM
KEY_SIZE = 32  # 256 bits for AES-256
ITERATIONS = 600_000  # OWASP recommended minimum for PBKDF2-SHA256


def derive_key(passphrase: str, salt: bytes) -> bytes:
    """
    Derive a 256-bit encryption key from a passphrase using PBKDF2.
    
    Args:
        passphrase: User-provided passphrase
        salt: Random salt (must be stored with ciphertext)
    
    Returns:
        32-byte encryption key
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_SIZE,
        salt=salt,
        iterations=ITERATIONS,
        backend=default_backend()
    )
    return kdf.derive(passphrase.encode('utf-8'))


def encrypt_data(data: bytes, passphrase: str) -> bytes:
    """
    Encrypt data using AES-256-GCM with a user-provided passphrase.
    
    The output format is:
        [salt:32][nonce:12][ciphertext:N][tag:16]
    
    Args:
        data: Plaintext data to encrypt
        passphrase: User-provided passphrase
    
    Returns:
        Encrypted data with salt and nonce prepended
    """
    # Generate random salt and nonce
    salt = os.urandom(SALT_SIZE)
    nonce = os.urandom(NONCE_SIZE)
    
    # Derive key from passphrase
    key = derive_key(passphrase, salt)
    
    # Encrypt using AES-256-GCM
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    
    # Return salt + nonce + ciphertext (includes auth tag)
    return salt + nonce + ciphertext


def decrypt_data(encrypted_data: bytes, passphrase: str) -> bytes:
    """
    Decrypt data that was encrypted with encrypt_data().
    
    Args:
        encrypted_data: Output from encrypt_data()
        passphrase: User-provided passphrase
    
    Returns:
        Decrypted plaintext data
    
    Raises:
        ValueError: If passphrase is incorrect or data is corrupted
    """
    if len(encrypted_data) < SALT_SIZE + NONCE_SIZE + 16:
        raise ValueError("Encrypted data is too short")
    
    # Extract components
    salt = encrypted_data[:SALT_SIZE]
    nonce = encrypted_data[SALT_SIZE:SALT_SIZE + NONCE_SIZE]
    ciphertext = encrypted_data[SALT_SIZE + NONCE_SIZE:]
    
    # Derive key from passphrase
    key = derive_key(passphrase, salt)
    
    # Decrypt
    try:
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as e:
        raise ValueError("Decryption failed - incorrect passphrase or corrupted data") from e


def encrypt_json(data: dict, passphrase: str) -> bytes:
    """
    Encrypt a Python dict as JSON using AES-256-GCM.
    
    Args:
        data: Dictionary to encrypt
        passphrase: User-provided passphrase
    
    Returns:
        Encrypted data
    """
    json_bytes = json.dumps(data, ensure_ascii=False, default=str).encode('utf-8')
    return encrypt_data(json_bytes, passphrase)


def decrypt_json(encrypted_data: bytes, passphrase: str) -> dict:
    """
    Decrypt JSON data that was encrypted with encrypt_json().
    
    Args:
        encrypted_data: Output from encrypt_json()
        passphrase: User-provided passphrase
    
    Returns:
        Decrypted dictionary
    """
    decrypted = decrypt_data(encrypted_data, passphrase)
    return json.loads(decrypted.decode('utf-8'))


def compute_checksum(data: bytes) -> str:
    """Compute SHA-256 checksum of data."""
    return hashlib.sha256(data).hexdigest()


def verify_checksum(data: bytes, expected: str) -> bool:
    """Verify SHA-256 checksum matches."""
    return compute_checksum(data) == expected
