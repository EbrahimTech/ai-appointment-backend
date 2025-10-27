"""Database field shims to support non-Postgres test environments."""

from __future__ import annotations

from django.contrib.postgres.fields import ArrayField
from pgvector.django import VectorField


class CompatArrayField(ArrayField):
    """ArrayField that degrades to JSON when Postgres is unavailable."""

    def db_type(self, connection):
        if connection.vendor != "postgresql":
            return "json"
        return super().db_type(connection)


class CompatVectorField(VectorField):
    """VectorField fallback storing text for non-Postgres backends."""

    def db_type(self, connection):
        if connection.vendor != "postgresql":
            return "text"
        return super().db_type(connection)
