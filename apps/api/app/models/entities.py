"""SQLAlchemy entities: users, question profiles, quizzes, attempts.

Base.metadata is what `alembic revision --autogenerate` diffs the database against, so every class
here has a table in a migration and vice versa. Only `users` is written today (app/deps.py); the
other three are the schema Step 3 fills in.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, MetaData, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Long enough for a UUID (36) with room to spare, short enough that the column is not a place to hide
# a payload. app.deps enforces the same cap at the boundary; keep the two in step.
USER_ID_MAX = 64
ID_MAX = 64

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    # Set before the first migration on purpose: without it Postgres invents constraint names that a
    # later ALTER cannot reliably target, and adding a convention afterwards renames everything.
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class User(Base):
    """One row per X-User-Id ever seen, created on first sight.

    `email` is nullable because there is no sign-up: a get-or-create keyed on the extension's random
    UUID has nothing to put there, and a NOT NULL column made the insert impossible.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(USER_ID_MAX), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QuestionProfileRow(Base):
    __tablename__ = "question_profiles"

    id: Mapped[str] = mapped_column(String(ID_MAX), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    config: Mapped[dict] = mapped_column(JSONB)


class QuizRow(Base):
    __tablename__ = "quizzes"

    id: Mapped[str] = mapped_column(String(ID_MAX), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB)  # full quiz JSON (contract shape)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[str] = mapped_column(String(ID_MAX), primary_key=True)
    quiz_id: Mapped[str] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    answers: Mapped[dict] = mapped_column(JSONB)  # {question_id: chosen_index}
    score: Mapped[int]
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
