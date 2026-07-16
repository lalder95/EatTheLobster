import pathlib
import tempfile

import pytest

from app.core.dedupe_service import DedupeService


@pytest.fixture()
def svc():
    return DedupeService()


def _temp_file(content: bytes) -> pathlib.Path:
    f = tempfile.NamedTemporaryFile(delete=False)
    f.write(content)
    f.close()
    return pathlib.Path(f.name)


def test_hash_is_64_hex_chars(svc):
    path = _temp_file(b"hello world")
    try:
        h = svc.compute_hash(path)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)
    finally:
        path.unlink(missing_ok=True)


def test_same_content_same_hash(svc):
    p1 = _temp_file(b"same content")
    p2 = _temp_file(b"same content")
    try:
        assert svc.compute_hash(p1) == svc.compute_hash(p2)
    finally:
        p1.unlink(missing_ok=True)
        p2.unlink(missing_ok=True)


def test_different_content_different_hash(svc):
    p1 = _temp_file(b"content A")
    p2 = _temp_file(b"content B")
    try:
        assert svc.compute_hash(p1) != svc.compute_hash(p2)
    finally:
        p1.unlink(missing_ok=True)
        p2.unlink(missing_ok=True)


def test_empty_file_has_stable_hash(svc):
    p = _temp_file(b"")
    try:
        h1 = svc.compute_hash(p)
        h2 = svc.compute_hash(p)
        assert h1 == h2
    finally:
        p.unlink(missing_ok=True)
