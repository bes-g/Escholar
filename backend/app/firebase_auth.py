"""Verify Firebase ID tokens with Google's public keys. The private key never leaves Google."""

import json
from pathlib import Path

import jwt
from jwt import PyJWKClient

from app.config import settings

CERTS_URL = "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
_certs: PyJWKClient | None = None


class FirebaseAuthError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def project_id() -> str:
    explicit = (settings.firebase_project_id or "").strip()
    if explicit:
        return explicit
    path = (settings.firebase_service_account_file or "").strip()
    if not path:
        return ""
    try:
        data = json.loads(Path(path).expanduser().read_text())
    except (OSError, json.JSONDecodeError):
        return ""
    found = data.get("project_id")
    return found.strip() if isinstance(found, str) else ""


def firebase_configured() -> bool:
    return bool(project_id())


def _client() -> PyJWKClient:
    global _certs
    if _certs is None:
        _certs = PyJWKClient(CERTS_URL, cache_keys=True, lifespan=3600)
    return _certs


def verify_firebase_token(token: str) -> dict:
    project = project_id()
    if not project:
        raise FirebaseAuthError("Firebase sign-in is not configured on the server.")
    if not token or len(token) > 8192:
        raise FirebaseAuthError("Sign-in could not be verified.")
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256":
            raise FirebaseAuthError("Sign-in could not be verified.")
        signing_key = _client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=project,
            issuer=f"https://securetoken.google.com/{project}",
            leeway=10,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except FirebaseAuthError:
        raise
    except Exception as exc:
        raise FirebaseAuthError("Sign-in could not be verified.") from exc
    email = str(claims.get("email") or "").strip().lower()
    uid = str(claims.get("sub") or "").strip()
    if not email or not uid:
        raise FirebaseAuthError("The Firebase account has no email address.")
    return {"uid": uid, "email": email}
