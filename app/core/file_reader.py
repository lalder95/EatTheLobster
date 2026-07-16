import pathlib
from typing import List, Union

import pandas as pd
import logging

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


class FileReader:
    def read_file(self, file_path: Union[str, pathlib.Path]) -> pd.DataFrame:
        path = pathlib.Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type '{ext}'. "
                f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
            )

        if ext == ".csv":
            return self._read_csv(path)
        return self._read_excel(path)

    def _read_csv(self, path: pathlib.Path) -> pd.DataFrame:
        encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
        last_error: Exception = Exception("No encoding tried")
        for encoding in encodings:
            try:
                df = pd.read_csv(path, encoding=encoding, dtype=str)
                df.columns = [str(c).strip() for c in df.columns]
                logger.debug(
                    f"Read CSV {path} with encoding={encoding}: {len(df)} rows"
                )
                return df
            except UnicodeDecodeError as exc:
                last_error = exc
                continue
        raise ValueError(
            f"Could not decode '{path}' with any supported encoding"
        ) from last_error

    def _read_excel(self, path: pathlib.Path) -> pd.DataFrame:
        df = pd.read_excel(path, sheet_name=0, dtype=str)
        df.columns = [str(c).strip() for c in df.columns]
        logger.debug(f"Read Excel {path}: {len(df)} rows")
        return df

    def get_columns(self, file_path: Union[str, pathlib.Path]) -> List[str]:
        df = self.read_file(file_path)
        return list(df.columns)
