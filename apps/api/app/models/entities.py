"""SQLAlchemy entities per the architecture: users, quizzes, attempts, history."""

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class QuestionProfileRow(Base):
    __tablename__ = "question_profiles"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    config: Mapped[dict] = mapped_column(JSON)


class QuizRow(Base):
    __tablename__ = "quizzes"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    source_url: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)  # full quiz JSON (contract shape)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    quiz_id: Mapped[str] = mapped_column(ForeignKey("quizzes.id"))
    answers: Mapped[dict] = mapped_column(JSON)  # {question_id: chosen_index}
    score: Mapped[int]
    completed_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
