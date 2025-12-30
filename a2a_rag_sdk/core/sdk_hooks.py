"""SDK Hooks - Sistema de hooks e auditoria para RAG SDK"""
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .config import get_config


class AuditEventType(str, Enum):
    """Tipos de eventos de auditoria"""
    SEARCH = "search"
    INGEST = "ingest"
    CHAT = "chat"
    QUIZ = "quiz"
    ERROR = "error"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    # Security/RBAC types
    TOOL_BLOCKED = "tool_blocked"
    RBAC_VIOLATION = "rbac_violation"
    RATE_LIMITED = "rate_limited"
    SECURITY_BLOCKED = "security_blocked"
    # Tool events
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"


@dataclass
class AuditEvent:
    """Evento de auditoria"""
    event_type: AuditEventType
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    action: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type.value,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "action": self.action,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "error": self.error,
        }


class AuditDatabase:
    """Banco de dados de auditoria"""

    def __init__(self, db_path: str = None):
        config = get_config()
        self.db_path = Path(db_path) if db_path else config.rag_db_path.parent / "audit.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Inicializa tabelas de auditoria"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                user_id TEXT,
                session_id TEXT,
                action TEXT,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                success INTEGER DEFAULT 1,
                error TEXT
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_events(event_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_events(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_events(session_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp)
        """)

        conn.commit()
        conn.close()

    def log_event(self, event: AuditEvent) -> int:
        """Registra evento de auditoria"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO audit_events
            (event_type, user_id, session_id, action, details, timestamp, success, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            event.event_type.value,
            event.user_id,
            event.session_id,
            event.action,
            json.dumps(event.details),
            event.timestamp.isoformat(),
            1 if event.success else 0,
            event.error,
        ])

        event_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return event_id

    def get_events(
        self,
        event_type: Optional[AuditEventType] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[dict]:
        """Busca eventos de auditoria"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        query = "SELECT * FROM audit_events WHERE 1=1"
        params = []

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type.value)
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        events = [dict(zip(columns, row)) for row in cursor.fetchall()]

        conn.close()
        return events

    def get_stats(self, days: int = 7, session_id: Optional[str] = None) -> dict:
        """Retorna estatísticas de auditoria"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        session_filter = ""
        params_base = [f"-{days} days"]
        if session_id:
            session_filter = " AND session_id = ?"
            params_base.append(session_id)

        cursor.execute(f"""
            SELECT event_type, COUNT(*) as count
            FROM audit_events
            WHERE timestamp > datetime('now', ?){session_filter}
            GROUP BY event_type
        """, params_base)

        by_type = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.execute(f"""
            SELECT COUNT(*) FROM audit_events
            WHERE timestamp > datetime('now', ?){session_filter}
        """, params_base)
        total = cursor.fetchone()[0]

        cursor.execute(f"""
            SELECT COUNT(*) FROM audit_events
            WHERE success = 0 AND timestamp > datetime('now', ?){session_filter}
        """, params_base)
        errors = cursor.fetchone()[0]

        conn.close()

        return {
            "total_events": total,
            "errors": errors,
            "by_type": by_type,
            "period_days": days,
            "session_id": session_id,
        }

    def query_events(
        self,
        event_type: Optional[AuditEventType] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        """Query events with filters (alias for get_events with tool_name support)"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        query = "SELECT * FROM audit_events WHERE 1=1"
        params = []

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type.value)
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        if tool_name:
            query += " AND json_extract(details, '$.tool_name') = ?"
            params.append(tool_name)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        events = [dict(zip(columns, row)) for row in cursor.fetchall()]

        conn.close()
        return events


# Hook types
HookCallback = Callable[[AuditEvent], None]


class SimpleRateLimiter:
    """Rate limiter simples baseado em memória"""

    def __init__(self, max_calls_per_hour: int = 100):
        self.max_calls_per_hour = max_calls_per_hour
        self._usage: Dict[str, Dict[str, int]] = {}

    def get_usage(self, user_id: str) -> Dict[str, int]:
        """Retorna uso por ferramenta para um usuário"""
        return self._usage.get(user_id, {})

    def record_call(self, user_id: str, tool_name: str):
        """Registra chamada de ferramenta"""
        if user_id not in self._usage:
            self._usage[user_id] = {}
        self._usage[user_id][tool_name] = self._usage[user_id].get(tool_name, 0) + 1

    def check_limit(self, user_id: str, tool_name: str) -> bool:
        """Verifica se usuário pode fazer mais chamadas"""
        usage = self._usage.get(user_id, {})
        return usage.get(tool_name, 0) < self.max_calls_per_hour

    def reset(self, user_id: Optional[str] = None):
        """Reset usage"""
        if user_id:
            self._usage.pop(user_id, None)
        else:
            self._usage.clear()


class HooksManager:
    """Gerenciador de hooks para eventos do SDK"""

    def __init__(self, max_calls_per_hour: int = 100, enable_rate_limit: bool = True):
        self._hooks: Dict[AuditEventType, List[HookCallback]] = {}
        self._audit_db: Optional[AuditDatabase] = None
        self.max_calls_per_hour = max_calls_per_hour
        self.enable_rate_limit = enable_rate_limit
        self.rate_limiter = SimpleRateLimiter(max_calls_per_hour)

    def register_hook(self, event_type: AuditEventType, callback: HookCallback):
        """Registra hook para tipo de evento"""
        if event_type not in self._hooks:
            self._hooks[event_type] = []
        self._hooks[event_type].append(callback)

    def unregister_hook(self, event_type: AuditEventType, callback: HookCallback):
        """Remove hook"""
        if event_type in self._hooks:
            self._hooks[event_type] = [h for h in self._hooks[event_type] if h != callback]

    def trigger(self, event: AuditEvent):
        """Dispara evento para hooks registrados"""
        # Salvar no banco de auditoria
        if self._audit_db:
            try:
                self._audit_db.log_event(event)
            except Exception:
                pass  # Não falhar por erro de auditoria

        # Chamar hooks registrados
        hooks = self._hooks.get(event.event_type, [])
        for hook in hooks:
            try:
                hook(event)
            except Exception:
                pass  # Não falhar por erro em hook

    def enable_audit_logging(self, db_path: str = None):
        """Habilita logging automático de auditoria"""
        self._audit_db = AuditDatabase(db_path)

    def disable_audit_logging(self):
        """Desabilita logging de auditoria"""
        self._audit_db = None

    @property
    def audit_db(self) -> Optional[AuditDatabase]:
        """Retorna banco de auditoria se habilitado"""
        return self._audit_db


# Singletons
_hooks_manager: Optional[HooksManager] = None
_audit_database: Optional[AuditDatabase] = None


def get_hooks_manager() -> HooksManager:
    """Get or create hooks manager singleton"""
    global _hooks_manager
    if _hooks_manager is None:
        _hooks_manager = HooksManager()
    return _hooks_manager


def get_audit_database() -> AuditDatabase:
    """Get or create audit database singleton"""
    global _audit_database
    if _audit_database is None:
        _audit_database = AuditDatabase()
    return _audit_database


def log_audit_event(
    event_type: AuditEventType,
    action: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    success: bool = True,
    error: Optional[str] = None,
) -> None:
    """Helper para logar evento de auditoria"""
    event = AuditEvent(
        event_type=event_type,
        user_id=user_id,
        session_id=session_id,
        action=action,
        details=details or {},
        success=success,
        error=error,
    )
    get_hooks_manager().trigger(event)
