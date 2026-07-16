import logging
from typing import List

import pandas as pd

logger = logging.getLogger(__name__)


class MappingService:
    def apply_mapping(self, df: pd.DataFrame, mappings) -> pd.DataFrame:
        rename_map: dict = {}
        for m in mappings:
            if m.source_column in df.columns:
                rename_map[m.source_column] = m.target_column
            else:
                logger.warning(
                    f"Source column '{m.source_column}' not found in DataFrame"
                )

        if not rename_map:
            return df

        selected = list(rename_map.keys())
        return df[selected].rename(columns=rename_map)

    def validate_mapping(self, df: pd.DataFrame, mappings) -> List[str]:
        errors: List[str] = []
        for m in mappings:
            if m.source_column not in df.columns:
                errors.append(
                    f"Source column '{m.source_column}' not found "
                    f"(available: {', '.join(list(df.columns)[:8])})"
                )
        return errors

    def suggest_mappings(
        self, source_columns: List[str], target_columns: List[str]
    ) -> List[dict]:
        suggestions: List[dict] = []
        used_targets: set = set()

        for src in source_columns:
            src_normalized = (
                src.lower().strip().replace(" ", "_").replace("-", "_")
            )
            matched = False

            for tgt in target_columns:
                if tgt.lower() == src_normalized and tgt not in used_targets:
                    suggestions.append({"source": src, "target": tgt})
                    used_targets.add(tgt)
                    matched = True
                    break

            if not matched:
                suggestions.append({"source": src, "target": src_normalized})

        return suggestions
