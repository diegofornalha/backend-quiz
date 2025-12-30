"""Core module - shared state and helper functions.

Migrated from Claude Agent SDK to LiteLLM with Gemini.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentfs_sdk import AgentFS

from llm import LiteLLMProvider
from llm.config import get_llm_config, translate_model_name

# =============================================================================
# CONFIGURATION
# =============================================================================

AGENTFS_DIR = Path.cwd() / ".agentfs"

# Sessions directory
SESSIONS_DIR = (
    Path.home()
    / ".claude"
    / "projects"
    / "-Users-2a--claude-hello-agent-chat-simples-backend-artifacts"
)

# Global instances
llm_provider: LiteLLMProvider | None = None
agentfs: AgentFS | None = None
current_session_id: str | None = None
current_model: str = "gemini/gemini-2.0-flash"


# =============================================================================
# LLM PROVIDER MANAGEMENT
# =============================================================================


def get_llm(model: str | None = None) -> LiteLLMProvider:
    """Get LiteLLM provider instance.

    Args:
        model: Optional model override (e.g., "haiku" -> translated to Gemini)

    Returns:
        LiteLLMProvider instance
    """
    global llm_provider, current_model

    # Translate old model names to Gemini
    if model:
        translated = translate_model_name(model)
        if translated != current_model:
            current_model = translated
            llm_provider = LiteLLMProvider(model=translated)
            print(f"[LLM] Model changed to: {translated}")

    if llm_provider is None:
        config = get_llm_config()
        current_model = config.model
        llm_provider = LiteLLMProvider(model=config.model)
        print(f"[LLM] Initialized with model: {config.model}")

    return llm_provider


# =============================================================================
# SESSION MANAGEMENT
# =============================================================================


def generate_session_id() -> str:
    """Generate a new session ID."""
    return str(uuid.uuid4())


async def get_session(
    model: str | None = None,
    project: str | None = None,
    session_id: str | None = None,
) -> tuple[LiteLLMProvider, "AgentFS", str]:
    """Get or create session with LLM and AgentFS.

    Args:
        model: Optional model name (old names like "haiku" are translated)
        project: Optional project name to save in session
        session_id: Optional existing session ID to use

    Returns:
        Tuple of (LiteLLMProvider, AgentFS, session_id)
    """
    global agentfs, current_session_id

    from agentfs_sdk import AgentFS, AgentFSOptions

    # Get or create LLM provider
    llm = get_llm(model)

    # Use provided session_id or current or generate new
    target_session_id = session_id or current_session_id or generate_session_id()

    # Check if we need to create/switch AgentFS
    if agentfs is None or current_session_id != target_session_id:
        # Close old agentfs if exists
        if agentfs is not None:
            try:
                await agentfs.close()
            except Exception as e:
                print(f"[WARN] Error closing agentfs: {e}")

        # Open new AgentFS
        agentfs = await AgentFS.open(AgentFSOptions(id=target_session_id))
        current_session_id = target_session_id

        # Save session info
        await agentfs.kv.set(
            "session:info",
            {
                "id": target_session_id,
                "model": current_model,
                "created_at": time.time(),
            },
        )

        # Save project if provided
        if project:
            await agentfs.kv.set("session:project", project)
            print(f"[INFO] Project set: {project}")

        # Write session log
        await agentfs.fs.write_file(
            "/logs/session_start.txt",
            f"Session {target_session_id} | Model: {current_model} | {time.strftime('%Y-%m-%d %H:%M:%S')}",
        )

        # Save current session file
        session_file = AGENTFS_DIR / "current_session"
        session_file.parent.mkdir(parents=True, exist_ok=True)
        session_file.write_text(target_session_id)

        print(f"[INFO] Session: {target_session_id} | Model: {current_model}")

    return llm, agentfs, current_session_id


async def get_agentfs() -> "AgentFS":
    """Get AgentFS instance, creating session if needed."""
    global agentfs

    if agentfs is None:
        _, agentfs, _ = await get_session()

    return agentfs


async def clear_session():
    """Clear current session WITHOUT creating a new one."""
    global llm_provider, agentfs, current_session_id

    old_session = current_session_id

    if agentfs is not None:
        try:
            await agentfs.close()
        except Exception as e:
            print(f"[WARN] Error closing agentfs: {e}")
        agentfs = None

    current_session_id = None
    print(f"[INFO] Session cleared: {old_session}")


async def reset_session(project: str | None = None):
    """Reset session - clear old and create new.

    Args:
        project: Optional project name for new session
    """
    global current_session_id

    old_session = current_session_id

    # Clear current session
    await clear_session()

    # Force new session ID
    current_session_id = None

    # Create new session
    await get_session(project=project)
    print(f"[INFO] Session reset: {old_session} -> {current_session_id}")


def get_current_session_id() -> str | None:
    """Get current session ID."""
    global current_session_id

    if current_session_id:
        return current_session_id

    session_file = AGENTFS_DIR / "current_session"
    if session_file.exists():
        try:
            return session_file.read_text().strip()
        except OSError:
            pass

    return None


# =============================================================================
# RAG MANAGEMENT
# =============================================================================


async def get_rag():
    """Get RAG instance with fixed ID for persistent documents.

    Note: RAG functionality is preserved but uses local search engine
    instead of A2A RAG SDK.
    """
    from agentfs_sdk import AgentFS, AgentFSOptions

    # Use fixed ID so documents persist across server restarts
    return await AgentFS.open(AgentFSOptions(id="rag-knowledge-base"))


# =============================================================================
# CLEANUP
# =============================================================================


async def cleanup():
    """Cleanup resources on shutdown."""
    global llm_provider, agentfs

    if agentfs is not None:
        try:
            await agentfs.close()
            print("[INFO] AgentFS closed!")
        except Exception as e:
            print(f"[WARN] Error closing agentfs: {e}")

    llm_provider = None
    print("[INFO] LLM provider released")


# =============================================================================
# BACKWARDS COMPATIBILITY
# =============================================================================

# Alias for backwards compatibility with old code
client = None  # No longer used, but kept for import compatibility


async def get_client(
    model: str | None = None,
    project: str | None = None,
    resume_session: str | None = None,
    fork_session: bool = False,
) -> LiteLLMProvider:
    """Backwards compatible function - returns LLM provider.

    Note: resume_session and fork_session are ignored as we no longer
    use Claude SDK session management.
    """
    llm, _, _ = await get_session(model=model, project=project, session_id=resume_session)
    return llm
