# packages/auth

Provider-independent auth: `IUserStore` (`User` persistence) +
`IAuthProvider` (register/authenticate/verify_token). Same "interface +
working local default, swap later" pattern as `ILLMProvider`,
`IVideoEngine`, `IComputeProvider` - `apps/api` depends only on
`IAuthProvider`, never on password hashing or token storage details.

## Implementations

| Interface | Implementation | Notes |
|---|---|---|
| `IUserStore` | `InMemoryUserStore` | Dev default; Postgres-backed is a later swap, same pattern as `IProjectStore` |
| `IAuthProvider` | `LocalAuthProvider` | PBKDF2-HMAC-SHA256 password hashing (stdlib `hashlib`, no bcrypt/argon2 build dependency), opaque bearer tokens in memory |

A production deployment would add an OAuth/OIDC-backed `IAuthProvider`
(Auth0, Clerk, ...) implementing the same interface - `apps/api`'s route
handlers and dependency injection would not change.

## Personal workspace per user

`LocalAuthProvider.register` assigns every new user a personal default
workspace (`ws_<user_id>`). There is no team/workspace-membership model
yet (inviting other users into a shared workspace, roles, ...) - see
`docs/adr/0011-frontend-and-auth.md` for why that's intentionally out of
scope for this pass rather than half-built.

## Status (Phase 5)

Implemented and tested (`tests/test_auth.py`): register, duplicate-email
rejection, login with correct/incorrect password, token verification,
unknown-token handling.
