import hashlib
import pathlib
from typing import Union

CHUNK_SIZE = 65_536


class DedupeService:
    def compute_hash(self, file_path: Union[str, pathlib.Path]) -> str:
        path = pathlib.Path(file_path)
        hasher = hashlib.sha256()
        with open(path, "rb") as fh:
            while chunk := fh.read(CHUNK_SIZE):
                hasher.update(chunk)
        return hasher.hexdigest()
