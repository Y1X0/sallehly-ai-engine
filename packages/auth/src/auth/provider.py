from __future__ import annotations

import hashlib
import secrets
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .store import IUserStore, User
from .token_store import InMemoryTokenStore, ITokenStore

_PBKDF2_ITERATIONS = 200_000


class AuthError(Exception):
    """Raised on registration/login failure: duplicate email, wrong
    password, or an unknown/expired token."""


@dataclass(frozen=True)
class AuthToken:
    token: str
    user_id: str


class IAuthProvider(ABC):
    """Provider-independent auth. Swapping `LocalAuthProvider` for an
    OAuth/OIDC-backed implementation (Auth0, Clerk, ...) means
    implementing this interface again - `apps/api` depends only on it,
    never on password hashing or token storage details directly. Same
    pattern as `ILLMProvider`/`IVideoEngine`/`IComputeProvider`.
    """

    @abstractmethod
    def register(self, email: str, password: str) -> User: ...

    @abstractmethod
    def authenticate(self, email: str, password: str) -> AuthToken: ...

    @abstractmethod
    def verify_token(self, token: str) -> User | None: ...

    @abstractmethod
    def refresh_token(self, token: str) -> AuthToken:
        """Issues a new token for the same user and invalidates `token`
        (rotation, not just extension) - raises `AuthError` if `token`
        is unknown or already expired. Phase 8 WP5,
        docs/adr/0020-security-hardening.md."""


class LocalAuthProvider(IAuthProvider):
    """Dev/local `IAuthProvider`: PBKDF2-HMAC-SHA256 password hashing
    (stdlib only - no bcrypt/argon2 build dependency), opaque bearer
    tokens held in an injected `ITokenStore` (`InMemoryTokenStore` by
    default - identical behavior to every pre-WP3 environment; a real
    `RedisTokenStore` fixes the multi-replica token-recognition gap,
    Phase 8 WP3). `token_ttl_seconds` (Phase 8 WP5, default `0` =
    never expires, unchanged from every pre-WP5 environment) is passed
    to every `ITokenStore.set()` call. Every new user gets a personal
    default workspace (`ws_<user_id>`) - see
    docs/adr/0011-frontend-and-auth.md for why a full team/workspace-
    membership model is intentionally out of scope for this pass.
    """

    def __init__(
        self,
        user_store: IUserStore,
        token_store: ITokenStore | None = None,
        *,
        token_ttl_seconds: int = 0,
    ) -> None:
        self._users = user_store
        self._tokens: ITokenStore = token_store if token_store is not None else InMemoryTokenStore()
        self._token_ttl_seconds = token_ttl_seconds or None

    def register(self, email: str, password: str) -> User:
        if self._users.get_by_email(email) is not None:
            raise AuthError(f"Email already registered: {email}")

        user_id = f"user_{uuid.uuid4().hex[:12]}"
        salt = secrets.token_hex(16)
        user = User(
            user_id=user_id,
            email=email,
            workspace_id=f"ws_{user_id}",
            password_hash=self._hash(password, salt),
            password_salt=salt,
        )
        self._users.create(user)
        return user

    def authenticate(self, email: str, password: str) -> AuthToken:
        user = self._users.get_by_email(email)
        if user is None or self._hash(password, user.password_salt) != user.password_hash:
            raise AuthError("Invalid email or password")

        return self._issue_token(user.user_id)

    def verify_token(self, token: str) -> User | None:
        user_id = self._tokens.get(token)
        if user_id is None:
            return None
        return self._users.get_by_id(user_id)

    def refresh_token(self, token: str) -> AuthToken:
        user_id = self._tokens.get(token)
        if user_id is None:
            raise AuthError("Invalid or expired token")
        self._tokens.delete(token)
        return self._issue_token(user_id)

    def _issue_token(self, user_id: str) -> AuthToken:
        token = secrets.token_urlsafe(32)
        self._tokens.set(token, user_id, ttl_seconds=self._token_ttl_seconds)
        return AuthToken(token=token, user_id=user_id)

    @staticmethod
    def _hash(password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ITERATIONS).hex()
