"""Shared MongoClient factory with robust TLS defaults for MongoDB Atlas.

``TLSV1_ALERT_INTERNAL_ERROR`` root causes and fixes
=====================================================
1. **Atlas Network Access** – add your current IP (or ``0.0.0.0/0`` for dev only).
2. **VPN / corporate SSL inspection** – disconnect VPN or try another network.
3. **Stale / missing CA bundle** – fixed here by always using ``certifi``.
   Do **not** set ``MONGO_TLS_USE_SYSTEM_CA=1`` on macOS: PyOpenSSL does not read
   the macOS Keychain and its fallback paths are usually empty, causing the server
   to send ``TLSV1_ALERT_INTERNAL_ERROR``.
4. **Missing PyOpenSSL stack** – run ``pip install -r requirements.txt`` so
   ``cryptography``, ``pyopenssl``, ``service-identity``, and ``requests`` are
   present (PyMongo uses PyOpenSSL for TLS when they are all installed).
5. **Outdated certifi** – run ``pip install -U certifi``.
"""

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


def _bool_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes")


def mongo_client_kwargs(mongo_uri: str) -> Dict[str, object]:
    """Keyword arguments for :class:`pymongo.mongo_client.MongoClient`.

    **CA certificates**
    ``certifi`` is always used as the TLS CA bundle.  It contains the correct
    Mozilla root certificates (DigiCert / ISRG) that MongoDB Atlas uses, and it
    works identically with both Python's stdlib ``ssl`` and the PyOpenSSL stack.

    ``MONGO_TLS_USE_SYSTEM_CA=1`` is intentionally *ignored* on macOS because
    PyOpenSSL calls ``set_default_verify_paths()`` which looks in OpenSSL's
    compiled-in paths (e.g. ``/usr/local/etc/openssl``), **not** the macOS
    Keychain, and those paths are usually empty — causing the server to reply
    with ``TLSV1_ALERT_INTERNAL_ERROR``.

    **OCSP**
    OCSP endpoint checks are disabled for ``mongodb+srv://`` URIs by default.
    Some networks (VPN, corporate proxy) block the OCSP URL and stall the
    handshake.  Set ``MONGO_TLS_STRICT_OCSP=1`` to re-enable them.
    """
    kw: Dict[str, object] = {}

    # Always use certifi — see docstring above for why MONGO_TLS_USE_SYSTEM_CA is skipped.
    kw["tlsCAFile"] = certifi.where()

    if not _bool_env("MONGO_TLS_STRICT_OCSP"):
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
    # Short timeout so startup never hangs if Atlas is temporarily unreachable
    kw.setdefault("serverSelectionTimeoutMS", 5000)
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
