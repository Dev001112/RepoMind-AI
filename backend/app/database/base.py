"""Declarative base shared by all ORM models. Alembic's env.py points at this."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
