"""File Watcher - Monitor files for automatic reindexing"""
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Set


@dataclass
class WatcherStatus:
    """Status do file watcher"""
    running: bool
    watched_paths: List[str]
    last_check: Optional[str]
    files_monitored: int
    changes_detected: int

    def to_dict(self) -> dict:
        return {
            "running": self.running,
            "watched_paths": self.watched_paths,
            "last_check": self.last_check,
            "files_monitored": self.files_monitored,
            "changes_detected": self.changes_detected,
        }


class FileWatcher:
    """Monitor de arquivos para auto-reindexação"""

    def __init__(
        self,
        watch_paths: List[str] = None,
        extensions: List[str] = None,
        on_change: Optional[Callable[[Path], None]] = None,
        check_interval: int = 30,
    ):
        self.watch_paths = [Path(p) for p in (watch_paths or [])]
        self.extensions = extensions or [".txt", ".md", ".pdf", ".py", ".json"]
        self.on_change = on_change
        self.check_interval = check_interval

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._file_mtimes: dict = {}
        self._changes_detected = 0
        self._last_check: Optional[datetime] = None

    def start(self):
        """Inicia monitoramento"""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Para monitoramento"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def is_active(self) -> bool:
        """Verifica se watcher está ativo"""
        return self._running

    def _watch_loop(self):
        """Loop de monitoramento"""
        while self._running:
            self._check_files()
            time.sleep(self.check_interval)

    def _check_files(self):
        """Verifica mudanças nos arquivos"""
        self._last_check = datetime.now()
        changed_files: Set[Path] = set()

        for watch_path in self.watch_paths:
            if not watch_path.exists():
                continue

            if watch_path.is_file():
                files = [watch_path]
            else:
                files = list(watch_path.rglob("*"))

            for file_path in files:
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() not in self.extensions:
                    continue

                try:
                    mtime = file_path.stat().st_mtime
                    key = str(file_path)

                    if key in self._file_mtimes:
                        if mtime > self._file_mtimes[key]:
                            changed_files.add(file_path)
                            self._changes_detected += 1

                    self._file_mtimes[key] = mtime
                except OSError:
                    pass

        # Notify on changes
        if changed_files and self.on_change:
            for file_path in changed_files:
                try:
                    self.on_change(file_path)
                except Exception:
                    pass

    def get_status(self) -> dict:
        """Retorna status do watcher"""
        return WatcherStatus(
            running=self._running,
            watched_paths=[str(p) for p in self.watch_paths],
            last_check=self._last_check.isoformat() if self._last_check else None,
            files_monitored=len(self._file_mtimes),
            changes_detected=self._changes_detected,
        ).to_dict()

    def add_path(self, path: str):
        """Adiciona caminho para monitorar"""
        p = Path(path)
        if p not in self.watch_paths:
            self.watch_paths.append(p)

    def remove_path(self, path: str):
        """Remove caminho do monitoramento"""
        p = Path(path)
        if p in self.watch_paths:
            self.watch_paths.remove(p)


# Singleton
_watcher: Optional[FileWatcher] = None


def get_watcher() -> FileWatcher:
    """Get or create file watcher singleton"""
    global _watcher
    if _watcher is None:
        _watcher = FileWatcher()
    return _watcher


def configure_watcher(
    watch_paths: List[str] = None,
    extensions: List[str] = None,
    on_change: Optional[Callable[[Path], None]] = None,
    check_interval: int = 30,
) -> FileWatcher:
    """Configure and return the file watcher"""
    global _watcher
    _watcher = FileWatcher(
        watch_paths=watch_paths,
        extensions=extensions,
        on_change=on_change,
        check_interval=check_interval,
    )
    return _watcher
