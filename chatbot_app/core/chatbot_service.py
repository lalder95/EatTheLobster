from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

try:  # pragma: no cover - optional dependency
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None

from chatbot_app.config import SCHEMA_SOURCE_PATH
from chatbot_app.core.schema_service import load_schema_context
from chatbot_app.core.sql_utils import build_sql_output_path, extract_final_sql
from chatbot_app.security import get_openai_api_key

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ChatbotResult:
    assistant_text: str
    sql_text: str | None = None
    output_path: Path | None = None


class ChatbotServiceError(RuntimeError):
    pass


class MissingApiKeyError(ChatbotServiceError):
    pass


class OutputFolderNotConfiguredError(ChatbotServiceError):
    pass


class SqlSaveError(ChatbotServiceError):
    pass


class ChatbotService:
    def load_schema_context(self) -> str:
        return load_schema_context(SCHEMA_SOURCE_PATH)

    def validate_api_key(self, api_key: str, model_name: str) -> None:
        if OpenAI is None:
            raise ChatbotServiceError("The openai package is not installed")
        client = OpenAI(api_key=api_key)
        client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "user", "content": "Reply with OK."},
            ],
            temperature=0,
            max_tokens=1,
        )

    def generate_sql(
        self,
        user_message: str,
        history: list[dict[str, str]],
        model_name: str,
        output_folder: Path | None,
    ) -> ChatbotResult:
        api_key = get_openai_api_key()
        if not api_key:
            raise MissingApiKeyError("OpenAI API key is not configured")
        if OpenAI is None:
            raise ChatbotServiceError("The openai package is not installed")

        schema_context = self.load_schema_context()
        system_prompt = self._build_system_prompt(schema_context)
        client = OpenAI(api_key=api_key)
        messages = [{"role": "system", "content": system_prompt}, *history]
        if not history or history[-1].get("role") != "user" or history[-1].get("content") != user_message:
            messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.2,
        )
        assistant_text = response.choices[0].message.content or ""
        sql_text = extract_final_sql(assistant_text)
        if sql_text is None:
            return ChatbotResult(assistant_text=assistant_text)
        if output_folder is None:
            raise OutputFolderNotConfiguredError(
                "Final SQL is ready. Configure an output folder in Settings to save it."
            )

        output_path = self._save_sql_file(output_folder, sql_text)
        logger.info("Saved generated SQL to %s", output_path)
        return ChatbotResult(
            assistant_text=assistant_text,
            sql_text=sql_text,
            output_path=output_path,
        )

    def _save_sql_file(self, output_folder: Path, sql_text: str) -> Path:
        try:
            output_path = build_sql_output_path(output_folder)
            expected_content = sql_text.rstrip() + "\n"
            output_path.write_text(expected_content, encoding="utf-8")
            if not output_path.is_file():
                raise OSError("The output file was not created")
            if output_path.read_text(encoding="utf-8") != expected_content:
                raise OSError("The saved output file could not be verified")
            return output_path
        except OSError as exc:
            raise SqlSaveError(
                f"SQL was generated but could not be saved to {output_folder}: {exc}"
            ) from exc

    def _build_system_prompt(self, schema_context: str) -> str:
        return (
            "You are a report-writing assistant for SQL Server and MySQL. "
            "Use the provided schema context to answer report design questions and generate SQL. "
            "The people using this chat are not technical. Use short, friendly, everyday "
            "language and ask one simple question at a time. Avoid technical words such as "
            "SQL, database, table, field, column, aggregation, query, filter, join, and "
            "format unless the user uses them first. Prefer plain wording: say 'show totals "
            "for each store' instead of 'aggregate by store'; say 'only include these dates' "
            "instead of 'apply a date filter'; and say 'sort from highest to lowest' instead "
            "of 'order descending'. Summarize the request in the same simple language before "
            "asking if it is ready. Have a normal conversation to gather the report "
            "requirements and ask concise clarifying questions when needed. Do not generate "
            "SQL until the user confirms that the requirements are complete or explicitly "
            "asks for the final report. "
            "When generating the final query, return it in exactly one ```sql fenced block "
            "with no text outside the block.\n\n"
            f"SCHEMA CONTEXT\n{schema_context}"
        )
