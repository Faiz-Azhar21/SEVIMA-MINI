"""Declarative Base untuk seluruh model ORM SQLAlchemy 2.0."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class seluruh model database SEVIMA-Mini."""
