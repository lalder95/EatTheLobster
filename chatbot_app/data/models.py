from __future__ import annotations

import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class ChatbotSettings(Base):
    __tablename__ = "chatbot_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    output_folder_path = Column(Text, nullable=False, default="")
    model_name = Column(String(128), nullable=False, default="gpt-4o-mini")
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.UTC),
        onupdate=lambda: datetime.datetime.now(datetime.UTC),
    )


class ChatbotConversation(Base):
    __tablename__ = "chatbot_conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256), nullable=False, default="Conversation")
    model_name = Column(String(128), nullable=False, default="gpt-4o-mini")
    output_folder_path = Column(Text, nullable=False, default="")
    schema_source_path = Column(Text, nullable=False, default="")
    last_sql_path = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.UTC),
        onupdate=lambda: datetime.datetime.now(datetime.UTC),
    )

    messages = relationship(
        "ChatbotMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatbotMessage.created_at",
    )


class ChatbotMessage(Base):
    __tablename__ = "chatbot_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        Integer, ForeignKey("chatbot_conversations.id"), nullable=False
    )
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))

    conversation = relationship("ChatbotConversation", back_populates="messages")
