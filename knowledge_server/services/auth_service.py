from __future__ import annotations

import hashlib
import uuid


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_id() -> str:
    return str(uuid.uuid4())


def verify_api_key(plain: str, hashed: str) -> bool:
    return hash_api_key(plain) == hashed
