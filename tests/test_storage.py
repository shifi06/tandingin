"""Unit tests for opaque file references and the Vercel private Blob adapter."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from storage import (
    LocalPrivateStorage,
    VercelPrivateBlobStorage,
    decode_file_token,
    encode_file_token,
    file_url,
)


class FakeBlobClient:
    def __init__(self):
        self.objects = {}
        self.calls = []

    def put_blob(self, pathname, body, **kwargs):
        self.calls.append(("put", pathname, kwargs))
        self.objects[pathname] = (body, kwargs.get("content_type"))
        return SimpleNamespace(pathname=pathname, url=f"https://test.private.blob.vercel-storage.com/{pathname}")

    def get_blob(self, pathname, **kwargs):
        self.calls.append(("get", pathname, kwargs))
        body, content_type = self.objects[pathname]
        return SimpleNamespace(body=body, metadata=SimpleNamespace(content_type=content_type))

    def delete_blob(self, pathname):
        self.calls.append(("delete", pathname, {}))
        self.objects.pop(pathname, None)


class StorageTest(unittest.TestCase):
    def test_file_tokens_round_trip_and_are_not_direct_blob_urls(self):
        ref = "vercel-blob://match-evidence/123.png"
        token = encode_file_token(ref)
        self.assertEqual(decode_file_token(token), ref)
        self.assertEqual(file_url(ref), f"/api/files/{token}")
        self.assertNotIn("private.blob.vercel-storage.com", file_url(ref))
        with self.assertRaises(ValueError):
            decode_file_token("../../private")

    def test_local_private_storage_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            store = LocalPrivateStorage(folder)
            ref = store.put(
                b"png-content",
                filename="evidence.png",
                content_type="image/png",
                prefix="match-evidence",
            )
            self.assertTrue(ref.startswith("local://"))
            self.assertEqual(store.get(ref).body, b"png-content")
            store.delete(ref)
            with self.assertRaises(FileNotFoundError):
                store.get(ref)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_vercel_adapter_enforces_private_access_for_put_and_get(self):
        client = FakeBlobClient()
        store = VercelPrivateBlobStorage(client=client)
        ref = store.put(
            b"image-bytes",
            filename="evidence.png",
            content_type="image/png",
            prefix="match-evidence",
        )
        self.assertTrue(ref.startswith("vercel-blob://match-evidence/"))
        self.assertEqual(store.get(ref).body, b"image-bytes")
        store.delete(ref)
        self.assertEqual([call[0] for call in client.calls], ["put", "get", "delete"])
        self.assertEqual(client.calls[0][2]["access"], "private")
        self.assertEqual(client.calls[1][2]["access"], "private")


if __name__ == "__main__":
    unittest.main()
