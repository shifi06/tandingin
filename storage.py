"""Private file storage adapters for Tanding.in.

Production on Vercel uses a Vercel Blob store created with access=private.
Local development and automated tests use a private local-filesystem adapter.
"""
from __future__ import annotations

import base64
import mimetypes
import os
import re
import uuid
from pathlib import Path
from typing import NamedTuple


class StoredFile(NamedTuple):
    body: bytes
    content_type: str
    filename: str


def encode_file_token(storage_ref: str) -> str:
    """Encode a storage reference for an opaque application route."""
    raw = base64.urlsafe_b64encode(storage_ref.encode("utf-8")).decode("ascii")
    return raw.rstrip("=")


def decode_file_token(token: str) -> str:
    if not token or len(token) > 2048 or not re.fullmatch(r"[A-Za-z0-9_-]+", token):
        raise ValueError("Invalid file token")
    padded = token + ("=" * (-len(token) % 4))
    value = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    if not (value.startswith("local://") or value.startswith("vercel-blob://")):
        raise ValueError("Unsupported storage reference")
    return value


def file_url(storage_ref: str | None) -> str | None:
    """Return the app-authenticated URL, never a direct private Blob URL."""
    if not storage_ref:
        return None
    return f"/api/files/{encode_file_token(storage_ref)}"


class LocalPrivateStorage:
    """Local-only private storage used for development and tests."""

    def __init__(self, folder: str | os.PathLike[str]):
        self.folder = Path(folder).resolve()
        self.folder.mkdir(parents=True, exist_ok=True)

    def put(self, body: bytes, *, filename: str, content_type: str, prefix: str) -> str:
        suffix = Path(filename).suffix.lower()
        safe_name = f"{uuid.uuid4().hex}{suffix}"
        destination = (self.folder / safe_name).resolve()
        if destination.parent != self.folder:
            raise ValueError("Invalid file path")
        destination.write_bytes(body)
        return f"local://{safe_name}"

    def get(self, storage_ref: str) -> StoredFile:
        if not storage_ref.startswith("local://"):
            raise ValueError("Wrong storage backend")
        name = storage_ref.removeprefix("local://")
        if not name or Path(name).name != name:
            raise ValueError("Invalid local storage reference")
        path = (self.folder / name).resolve()
        if path.parent != self.folder or not path.is_file():
            raise FileNotFoundError(name)
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        return StoredFile(path.read_bytes(), content_type, name)

    def delete(self, storage_ref: str) -> None:
        if not storage_ref.startswith("local://"):
            return
        name = storage_ref.removeprefix("local://")
        if not name or Path(name).name != name:
            return
        path = (self.folder / name).resolve()
        if path.parent == self.folder and path.is_file():
            path.unlink(missing_ok=True)


class VercelPrivateBlobStorage:
    """Vercel Blob adapter. All operations explicitly use private access."""

    def __init__(self, client=None):
        # Optional client injection keeps adapter tests independent of network/auth.
        self._injected_client = client

    def _client(self):
        if self._injected_client is not None:
            return self._injected_client
        from vercel.blob import sync as blob  # supplied by vercel-blob>=0.5.0
        return blob

    def put(self, body: bytes, *, filename: str, content_type: str, prefix: str) -> str:
        suffix = Path(filename).suffix.lower()
        pathname = f"{prefix.strip('/')}/{uuid.uuid4().hex}{suffix}"
        result = self._client().put_blob(
            pathname,
            body,
            access="private",
            content_type=content_type,
            add_random_suffix=False,
            cache_control_max_age=0,
        )
        return f"vercel-blob://{result.pathname}"

    def get(self, storage_ref: str) -> StoredFile:
        if not storage_ref.startswith("vercel-blob://"):
            raise ValueError("Wrong storage backend")
        pathname = storage_ref.removeprefix("vercel-blob://")
        result = self._client().get_blob(pathname, access="private")
        name = Path(pathname).name
        content_type = result.metadata.content_type or mimetypes.guess_type(name)[0] or "application/octet-stream"
        return StoredFile(result.body, content_type, name)

    def delete(self, storage_ref: str) -> None:
        if storage_ref.startswith("vercel-blob://"):
            pathname = storage_ref.removeprefix("vercel-blob://")
            self._client().delete_blob(pathname)


def get_storage():
    """Get the app-scoped adapter, lazily to avoid network calls at import time."""
    from flask import current_app

    existing = current_app.extensions.get("tandingin_storage")
    if existing is not None:
        return existing

    backend = current_app.config["STORAGE_BACKEND"]
    if backend == "local":
        adapter = LocalPrivateStorage(current_app.config["UPLOAD_FOLDER"])
    elif backend == "vercel_blob":
        adapter = VercelPrivateBlobStorage()
    else:
        raise RuntimeError(f"Unsupported STORAGE_BACKEND: {backend}")

    current_app.extensions["tandingin_storage"] = adapter
    return adapter
