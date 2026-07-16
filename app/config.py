import os
import pathlib
from cryptography.fernet import Fernet

APP_NAME = "ETLImporter"
APP_DATA_DIR = pathlib.Path(os.environ.get("APPDATA", str(pathlib.Path.home()))) / APP_NAME
METADATA_DB_PATH = APP_DATA_DIR / "metadata.db"
KEY_FILE_PATH = APP_DATA_DIR / ".key"
LOG_DIR = APP_DATA_DIR / "logs"


def _ensure_dirs() -> None:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _load_or_create_key() -> bytes:
    _ensure_dirs()
    if KEY_FILE_PATH.exists():
        return KEY_FILE_PATH.read_bytes()
    key = Fernet.generate_key()
    KEY_FILE_PATH.write_bytes(key)
    return key


def get_fernet() -> Fernet:
    return Fernet(_load_or_create_key())


def encrypt(plaintext: str) -> str:
    return get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return get_fernet().decrypt(token.encode()).decode()
