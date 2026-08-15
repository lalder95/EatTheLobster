from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from chatbot_app.data.models import ChatbotConversation, ChatbotMessage, ChatbotSettings


class ChatbotSettingsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self) -> ChatbotSettings:
        settings = self.session.query(ChatbotSettings).first()
        if settings is None:
            settings = ChatbotSettings()
            self.session.add(settings)
            self.session.commit()
            self.session.refresh(settings)
        return settings

    def save(
        self,
        output_folder_path: str,
        model_name: str,
        enabled: bool = True,
    ) -> ChatbotSettings:
        settings = self.get()
        settings.output_folder_path = output_folder_path
        settings.model_name = model_name
        settings.enabled = enabled
        settings.updated_at = datetime.datetime.now(datetime.UTC)
        self.session.commit()
        self.session.refresh(settings)
        return settings


class ChatbotConversationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        title: str,
        model_name: str,
        output_folder_path: str,
        schema_source_path: str,
    ) -> ChatbotConversation:
        conversation = ChatbotConversation(
            title=title,
            model_name=model_name,
            output_folder_path=output_folder_path,
            schema_source_path=schema_source_path,
        )
        self.session.add(conversation)
        self.session.commit()
        self.session.refresh(conversation)
        return conversation

    def get_by_id(self, conversation_id: int) -> ChatbotConversation | None:
        return (
            self.session.query(ChatbotConversation)
            .filter_by(id=conversation_id)
            .first()
        )

    def get_most_recent(self) -> ChatbotConversation | None:
        return (
            self.session.query(ChatbotConversation)
            .order_by(ChatbotConversation.updated_at.desc())
            .first()
        )

    def update_metadata(
        self,
        conversation_id: int,
        *,
        title: str | None = None,
        model_name: str | None = None,
        output_folder_path: str | None = None,
        schema_source_path: str | None = None,
        last_sql_path: str | None = None,
    ) -> ChatbotConversation | None:
        conversation = self.get_by_id(conversation_id)
        if conversation is None:
            return None
        if title is not None:
            conversation.title = title
        if model_name is not None:
            conversation.model_name = model_name
        if output_folder_path is not None:
            conversation.output_folder_path = output_folder_path
        if schema_source_path is not None:
            conversation.schema_source_path = schema_source_path
        if last_sql_path is not None:
            conversation.last_sql_path = last_sql_path
        conversation.updated_at = datetime.datetime.now(datetime.UTC)
        self.session.commit()
        self.session.refresh(conversation)
        return conversation


class ChatbotMessageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
    ) -> ChatbotMessage:
        message = ChatbotMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
        )
        self.session.add(message)
        self.session.commit()
        self.session.refresh(message)
        return message

    def get_for_conversation(self, conversation_id: int) -> list[ChatbotMessage]:
        return (
            self.session.query(ChatbotMessage)
            .filter_by(conversation_id=conversation_id)
            .order_by(ChatbotMessage.created_at.asc())
            .all()
        )
