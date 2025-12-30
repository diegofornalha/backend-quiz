"""Authentication stub"""
import os
from typing import Optional

# Carregar API keys do .env
VALID_API_KEYS = set()
api_keys_str = os.getenv("API_KEYS", "")
if api_keys_str:
    VALID_API_KEYS = set(key.strip() for key in api_keys_str.split(",") if key.strip())

def is_auth_enabled() -> bool:
    """Verifica se autenticação está habilitada"""
    return len(VALID_API_KEYS) > 0

def verify_api_key(api_key: Optional[str]) -> bool:
    """Verifica se API key é válida"""
    if not is_auth_enabled():
        return True
    return api_key in VALID_API_KEYS
