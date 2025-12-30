"""Validation utilities"""
import re
from pathlib import Path

def validate_session_id(session_id: str) -> bool:
    """Valida formato de session ID"""
    # Session IDs geralmente são UUIDs ou alfanuméricos com hífens
    pattern = r'^[a-zA-Z0-9\-_]+$'
    return bool(re.match(pattern, session_id)) and len(session_id) < 100

def validate_filename(filename: str) -> bool:
    """Valida nome de arquivo"""
    # Não permitir path traversal ou caracteres especiais perigosos
    dangerous_chars = ['..', '/', '\\', '\0', '<', '>', '|', ':', '*', '?', '"']
    if any(char in filename for char in dangerous_chars):
        return False
    return len(filename) > 0 and len(filename) < 255

def validate_directory_path(path: str) -> bool:
    """Valida caminho de diretório"""
    try:
        p = Path(path)
        # Não permitir caminhos absolutos ou path traversal
        if p.is_absolute():
            return False
        if '..' in p.parts:
            return False
        return len(str(p)) < 500
    except:
        return False
