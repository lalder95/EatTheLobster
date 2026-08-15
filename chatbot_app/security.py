from __future__ import annotations

from pathlib import Path

try:  # pragma: no cover - optional dependency
    import keyring
except Exception:  # pragma: no cover - optional dependency
    keyring = None

from chatbot_app.config import (
    OPENAI_KEY_ACCOUNT,
    OPENAI_KEY_FILE_PATH,
    OPENAI_KEY_SERVICE,
    decrypt,
    encrypt,
)


class ApiKeyStoreError(RuntimeError):
    pass


def get_openai_api_key() -> str | None:
    if keyring is not None:
        try:
            stored = keyring.get_password(OPENAI_KEY_SERVICE, OPENAI_KEY_ACCOUNT)
            if stored:
                return stored
        except Exception:
            pass

    if OPENAI_KEY_FILE_PATH.exists():
        try:
            return decrypt(OPENAI_KEY_FILE_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ApiKeyStoreError(str(exc)) from exc
    return None


def save_openai_api_key(api_key: str) -> None:
    if keyring is not None:
        try:
            keyring.set_password(OPENAI_KEY_SERVICE, OPENAI_KEY_ACCOUNT, api_key)
            return
        except Exception:
            pass

    try:
        OPENAI_KEY_FILE_PATH.write_text(encrypt(api_key), encoding="utf-8")
    except Exception as exc:
        raise ApiKeyStoreError(str(exc)) from exc
