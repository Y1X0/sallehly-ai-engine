from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class User:
    user_id: str
    email: str
    workspace_id: str
    password_hash: str
    password_salt: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_public_dict(self) -> dict[str, str]:
        """Never include password_hash/password_salt in anything sent to
        a client - this is the only view of a User the API is allowed
        to return."""
        return {
            "user_id": self.user_id,
            "email": self.email,
            "workspace_id": self.workspace_id,
            "created_at": self.created_at,
        }


class IUserStore(ABC):
    @abstractmethod
    def create(self, user: User) -> None: ...

    @abstractmethod
    def get_by_id(self, user_id: str) -> User | None: ...

    @abstractmethod
    def get_by_email(self, email: str) -> User | None: ...


class InMemoryUserStore(IUserStore):
    def __init__(self) -> None:
        self._by_id: dict[str, User] = {}
        self._by_email: dict[str, User] = {}

    def create(self, user: User) -> None:
        if user.email in self._by_email:
            raise ValueError(f"Email already registered: {user.email}")
        self._by_id[user.user_id] = user
        self._by_email[user.email] = user

    def get_by_id(self, user_id: str) -> User | None:
        return self._by_id.get(user_id)

    def get_by_email(self, email: str) -> User | None:
        return self._by_email.get(email)
