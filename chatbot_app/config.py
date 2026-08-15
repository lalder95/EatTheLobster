import getpass
import os
import pathlib

from cryptography.fernet import Fernet

APP_NAME = "ETLImporterChatbot"
APP_DATA_DIR = pathlib.Path(os.environ.get("APPDATA", str(pathlib.Path.home()))) / APP_NAME
METADATA_DB_PATH = APP_DATA_DIR / "metadata.db"
KEY_FILE_PATH = APP_DATA_DIR / ".key"
OPENAI_KEY_FILE_PATH = APP_DATA_DIR / ".openai_api_key"
LOG_DIR = APP_DATA_DIR / "logs"
SCHEMA_SOURCE_PATH = pathlib.Path(r"\\rksrvacct\Shared\ADS_Reports\_SourceFiles\db_schema.json")
OPENAI_KEY_SERVICE = "ETLImporterChatbot"
OPENAI_KEY_ACCOUNT = getpass.getuser() or "default"


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
