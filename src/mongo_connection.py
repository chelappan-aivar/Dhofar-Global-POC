"""Shared MongoClient TLS options for Atlas and strict networks."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import certifi
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import OperationFailure


def load_repo_root_env() -> None:
    """Load ``.env`` from the project root (directory above ``src``)."""
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env")


def mongo_client_kwargs(mongo_uri: str) -> Dict[str, object]:
    """Keyword arguments for :class:`pymongo.mongo_client.MongoClient`.

    For ``mongodb+srv://`` (Atlas), OCSP endpoint checks are turned off by default
    unless ``MONGO_TLS_STRICT_OCSP=1``. Some networks block OCSP and cause TLS
    handshake failures.

    Set ``MONGO_TLS_USE_SYSTEM_CA=1`` to omit ``tlsCAFile`` and use the OS CA
    store (e.g. macOS Keychain) instead of certifi.

    Set ``MONGO_TLS_DISABLE_OCSP=1`` to force OCSP checks off for any URI.
    """
    kw: Dict[str, object] = {}
    use_system_ca = os.getenv("MONGO_TLS_USE_SYSTEM_CA", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if not use_system_ca:
        kw["tlsCAFile"] = certifi.where()

    strict_ocsp = os.getenv("MONGO_TLS_STRICT_OCSP", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    force_disable_ocsp = os.getenv("MONGO_TLS_DISABLE_OCSP", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if strict_ocsp:
        pass
    elif force_disable_ocsp or mongo_uri.startswith("mongodb+srv://"):
        kw["tlsDisableOCSPEndpointCheck"] = True
    return kw


def mongo_credentials_from_env() -> tuple[str | None, str | None]:
    """Return (username, password) if both are set in the environment.

    PyMongo keyword ``username`` / ``password`` override any userinfo in the URI,
    so you can keep special characters in ``MONGO_PASSWORD`` without
    percent-encoding the connection string.

    Supported env vars: ``MONGO_USER`` or ``MONGO_USERNAME``, and ``MONGO_PASSWORD``.
    """
    user = (os.getenv("MONGO_USER") or os.getenv("MONGO_USERNAME") or "").strip() or None
    password = (os.getenv("MONGO_PASSWORD") or "").strip() or None
    if user and password:
        return user, password
    return None, None


def make_mongo_client(mongo_uri: str) -> MongoClient:
    """Build a :class:`~pymongo.mongo_client.MongoClient` with shared TLS options."""
    kw = mongo_client_kwargs(mongo_uri)
    user, password = mongo_credentials_from_env()
    if user is not None and password is not None:
        return MongoClient(mongo_uri, username=user, password=password, **kw)
    return MongoClient(mongo_uri, **kw)


def require_mongo_auth(client: Any) -> None:
    """Run ``admin.ping`` so bad credentials fail with a clear message."""
    try:
        client.admin.command("ping")
    except OperationFailure as exc:
        code = getattr(exc, "code", None)
        details = getattr(exc, "details", None) or {}
        errmsg = str(details.get("errmsg", "")).lower()
        if code == 8000 or "bad auth" in errmsg or "authentication failed" in errmsg:
            raise SystemExit(
                "MongoDB authentication failed (Atlas rejected the username or password).\n"
                "Fix:\n"
                "  • Atlas → Database Access: use that database user's name and password, "
                "not your Atlas website login.\n"
                "  • URL-encode special characters in the password inside MONGO_URI "
                "(e.g. @ → %40, # → %23, / → %2F), or set MONGO_USER + MONGO_PASSWORD in "
                ".env (plain text) — they override credentials in MONGO_URI.\n"
                "  • Reset the database user password and rebuild the URI from "
                "Connect → Drivers, or paste the URI and replace <password> only.\n"
                "  • In .env, avoid extra quotes or spaces around MONGO_URI or the password."
            ) from exc
        raise
