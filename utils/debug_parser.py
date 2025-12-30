"""Debug Parser - Parses CLI debug files for audit"""
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class DebugEntry:
    """Entrada de log de debug"""
    timestamp: str
    timestamp_ms: int
    level: str
    message: str
    tool_name: Optional[str] = None
    event_type: Optional[str] = None


def parse_debug_file(session_id: str, debug_dir: str = None) -> List[DebugEntry]:
    """Parse debug file for a session.

    Args:
        session_id: ID da sessão
        debug_dir: Diretório de debug (opcional)

    Returns:
        Lista de DebugEntry
    """
    if debug_dir is None:
        debug_dir = Path.home() / ".claude" / "debug"
    else:
        debug_dir = Path(debug_dir)

    entries = []

    # Try different file patterns
    patterns = [
        f"{session_id}.log",
        f"{session_id}.jsonl",
        f"debug_{session_id}.log",
    ]

    for pattern in patterns:
        file_path = debug_dir / pattern
        if file_path.exists():
            entries.extend(_parse_file(file_path))

    return sorted(entries, key=lambda e: e.timestamp_ms)


def _parse_file(file_path: Path) -> List[DebugEntry]:
    """Parse a single debug file."""
    entries = []

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")

        # Try JSONL format first
        if file_path.suffix == ".jsonl":
            for line in content.splitlines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    entry = _parse_json_entry(data)
                    if entry:
                        entries.append(entry)
                except json.JSONDecodeError:
                    pass
        else:
            # Parse text log format
            entries = _parse_text_log(content)

    except Exception:
        pass

    return entries


def _parse_json_entry(data: dict) -> Optional[DebugEntry]:
    """Parse a JSON log entry."""
    try:
        timestamp = data.get("timestamp", data.get("ts", ""))
        timestamp_ms = _parse_timestamp_ms(timestamp)

        return DebugEntry(
            timestamp=str(timestamp),
            timestamp_ms=timestamp_ms,
            level=data.get("level", data.get("severity", "INFO")),
            message=data.get("message", data.get("msg", "")),
            tool_name=data.get("tool_name", data.get("tool")),
            event_type=data.get("event_type", data.get("type")),
        )
    except Exception:
        return None


def _parse_text_log(content: str) -> List[DebugEntry]:
    """Parse text format log file."""
    entries = []

    # Common log format: [TIMESTAMP] LEVEL: message
    # Or: TIMESTAMP - LEVEL - message
    patterns = [
        r'\[([^\]]+)\]\s*(\w+):\s*(.*)',
        r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[^\s]*)\s*-?\s*(\w+)\s*-?\s*(.*)',
    ]

    for line in content.splitlines():
        if not line.strip():
            continue

        for pattern in patterns:
            match = re.match(pattern, line)
            if match:
                timestamp, level, message = match.groups()
                timestamp_ms = _parse_timestamp_ms(timestamp)

                # Detect event type from message
                event_type = _detect_event_type(message)
                tool_name = _extract_tool_name(message)

                entries.append(DebugEntry(
                    timestamp=timestamp,
                    timestamp_ms=timestamp_ms,
                    level=level.upper(),
                    message=message,
                    tool_name=tool_name,
                    event_type=event_type,
                ))
                break

    return entries


def _parse_timestamp_ms(timestamp: str) -> int:
    """Convert timestamp to milliseconds."""
    if not timestamp:
        return 0

    # If already numeric
    if isinstance(timestamp, (int, float)):
        return int(timestamp * 1000 if timestamp < 1e10 else timestamp)

    # Try ISO format
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except ValueError:
        pass

    # Try common formats
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(timestamp[:26], fmt)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue

    return 0


def _detect_event_type(message: str) -> Optional[str]:
    """Detect event type from message content."""
    message_lower = message.lower()

    if "pre_hook" in message_lower or "pre-hook" in message_lower:
        return "pre_hook"
    if "post_hook" in message_lower or "post-hook" in message_lower:
        return "post_hook"
    if "file_write" in message_lower or "file write" in message_lower or "wrote file" in message_lower:
        return "file_write"
    if "stream" in message_lower:
        return "stream"
    if "tool" in message_lower and "call" in message_lower:
        return "tool_call"
    if "error" in message_lower or "exception" in message_lower:
        return "error"

    return None


def _extract_tool_name(message: str) -> Optional[str]:
    """Extract tool name from message."""
    # Common patterns: "Tool: <name>", "tool=<name>", "calling <name>"
    patterns = [
        r'[Tt]ool[:\s=]+["\']?(\w+)["\']?',
        r'calling\s+["\']?(\w+)["\']?',
        r'tool_name[:\s=]+["\']?(\w+)["\']?',
    ]

    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return match.group(1)

    return None
