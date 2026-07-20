"""packages/auth: IUserStore + IAuthProvider (LocalAuthProvider,
InMemoryUserStore). Exercises the package directly, independent of
apps/api - see test_api.py for the HTTP-level auth contract.
"""

from __future__ import annotations

import pytest
import schemas
from auth import AuthError, InMemoryUserStore, LocalAuthProvider


def _provider() -> LocalAuthProvider:
    return LocalAuthProvider(InMemoryUserStore())


def test_register_creates_user_with_personal_workspace():
    provider = _provider()
    user = provider.register("a@b.com", "hunter22")

    assert user.email == "a@b.com"
    assert user.workspace_id == f"ws_{user.user_id}"
    assert user.password_hash != "hunter22"


def test_register_public_dict_validates_against_schema_and_hides_password():
    provider = _provider()
    user = provider.register("a@b.com", "hunter22")
    public = user.to_public_dict()

    schemas.validate(public, "user")
    assert "password_hash" not in public
    assert "password_salt" not in public


def test_register_rejects_duplicate_email():
    provider = _provider()
    provider.register("a@b.com", "hunter22")

    with pytest.raises(AuthError, match="already registered"):
        provider.register("a@b.com", "different-password")


def test_authenticate_succeeds_with_correct_password_and_issues_a_token():
    provider = _provider()
    provider.register("a@b.com", "hunter22")

    token = provider.authenticate("a@b.com", "hunter22")

    assert token.token
    assert token.user_id


def test_authenticate_rejects_wrong_password():
    provider = _provider()
    provider.register("a@b.com", "hunter22")

    with pytest.raises(AuthError, match="Invalid email or password"):
        provider.authenticate("a@b.com", "wrong-password")


def test_authenticate_rejects_unknown_email():
    provider = _provider()

    with pytest.raises(AuthError, match="Invalid email or password"):
        provider.authenticate("nobody@example.com", "hunter22")


def test_verify_token_resolves_back_to_the_same_user():
    provider = _provider()
    registered = provider.register("a@b.com", "hunter22")
    token = provider.authenticate("a@b.com", "hunter22")

    resolved = provider.verify_token(token.token)

    assert resolved is not None
    assert resolved.user_id == registered.user_id


def test_verify_token_returns_none_for_unknown_token():
    provider = _provider()

    assert provider.verify_token("not-a-real-token") is None
