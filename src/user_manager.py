# -*- coding: utf-8 -*-
"""Per-user Letta agent management and question-answer cache."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from src.letta_agent import create_user_agent, get_client

logger = logging.getLogger(__name__)


@dataclass
class UserSession:
    user_id: str
    agent_id: str
    created_at: float = field(default_factory=time.time)
    cache: dict[str, dict[str, Any]] = field(default_factory=dict)


class UserManager:
    """Thread-safe manager for per-user Letta agents and answer caches."""

    def __init__(self) -> None:
        self._sessions: dict[str, UserSession] = {}
        self._lock = threading.Lock()

    def _normalize_question(self, question: str) -> str:
        return question.strip().lower()

    def get_or_create_session(self, user_id: str) -> UserSession:
        with self._lock:
            session = self._sessions.get(user_id)
            if session:
                return session
        agent = create_user_agent(user_id)
        session = UserSession(user_id=user_id, agent_id=agent.id)
        with self._lock:
            existing = self._sessions.get(user_id)
            if existing:
                try:
                    get_client().agents.delete(agent.id)
                except Exception:
                    pass
                return existing
            self._sessions[user_id] = session
        logger.info("Created session for user=%s agent=%s", user_id, agent.id)
        return session

    def get_cached_answer(self, user_id: str, question: str) -> dict[str, Any] | None:
        with self._lock:
            session = self._sessions.get(user_id)
        if not session:
            return None
        key = self._normalize_question(question)
        return session.cache.get(key)

    def cache_answer(self, user_id: str, question: str, result: dict[str, Any]) -> None:
        with self._lock:
            session = self._sessions.get(user_id)
        if not session:
            return
        key = self._normalize_question(question)
        session.cache[key] = result

    def clear_user_memory(self, user_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(user_id, None)
        if not session:
            return False
        try:
            get_client().agents.delete(session.agent_id)
            logger.info("Deleted agent=%s for user=%s", session.agent_id, user_id)
        except Exception as e:
            logger.warning("Failed to delete agent=%s: %s", session.agent_id, e)
        return True

    def list_users(self) -> list[dict[str, Any]]:
        with self._lock:
            sessions = list(self._sessions.values())
        return [
            {
                "user_id": s.user_id,
                "agent_id": s.agent_id,
                "created_at": s.created_at,
                "cached_questions": len(s.cache),
            }
            for s in sessions
        ]

    def has_user(self, user_id: str) -> bool:
        with self._lock:
            return user_id in self._sessions


user_manager = UserManager()
