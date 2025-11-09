"""Database field shims to support non-Postgres test environments."""

from __future__ import annotations

import json

from datetime import datetime

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.fields.ranges import DateTimeRangeField
from django.utils import timezone
from pgvector.django import VectorField


class CompatArrayField(ArrayField):
    """ArrayField that degrades to JSON/text storage when Postgres is unavailable."""

    def db_type(self, connection):
        if connection.vendor != "postgresql":
            return "text"
        return super().db_type(connection)

    def get_prep_value(self, value):
        if value is None:
            return []
        return super().get_prep_value(value)
    
    # قبل:
    # def get_db_prep_save(self, value, connection, prepared=False):
    #     if connection.vendor == "postgresql":
    #         return super().get_db_prep_save(value, connection, prepared=prepared)
    #     if value is None:
    #         return json.dumps([])
    #     if not prepared:
    #         value = self.get_prep_value(value)
    #     return json.dumps(value)

    # بعد:
    def get_db_prep_save(self, value, connection):
        if connection.vendor == "postgresql":
            return super().get_db_prep_save(value, connection)
        if value is None:
            return json.dumps([])
        value = self.get_prep_value(value)
        return json.dumps(value)

    def get_placeholder(self, value, compiler, connection):
        if connection.vendor != "postgresql":
            return "%s"
        return super().get_placeholder(value, compiler, connection)

    def from_db_value(self, value, expression, connection):
        if connection.vendor == "postgresql":
            return value
        if value in (None, ""):
            return []
        if isinstance(value, list):
            return value
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value


class CompatVectorField(VectorField):
    """VectorField fallback storing text for non-Postgres backends."""

    def db_type(self, connection):
        if connection.vendor != "postgresql":
            return "text"
        return super().db_type(connection)


class CompatDateTimeRangeField(DateTimeRangeField):
    """DateTimeRangeField that stores JSON payloads when Postgres is unavailable."""

    def db_type(self, connection):
        if connection.vendor != "postgresql":
            return "text"
        return super().db_type(connection)

    # قبل:
    # def get_db_prep_value(self, value, connection, prepared=False):
    #     if connection.vendor == "postgresql":
    #         return super().get_db_prep_value(value, connection, prepared=prepared)
    #     if value is None:
    #         return None
    #     if not prepared:
    #         value = super().get_prep_value(value)
    #     lower = getattr(value, "lower", None)
    #     upper = getattr(value, "upper", None)
    #     if lower is None and upper is None and isinstance(value, (tuple, list)):
    #         lower, upper = value
    #     payload = {
    #         "lower": lower.isoformat() if lower else None,
    #         "upper": upper.isoformat() if upper else None,
    #     }
    #     return json.dumps(payload)

    # بعد:
    def get_db_prep_value(self, value, connection):
        if connection.vendor == "postgresql":
            return super().get_db_prep_value(value, connection)
        if value is None:
            return None
        value = super().get_prep_value(value)
        lower = getattr(value, "lower", None)
        upper = getattr(value, "upper", None)
        if lower is None and upper is None and isinstance(value, (tuple, list)):
            lower, upper = value
        payload = {
            "lower": lower.isoformat() if lower else None,
            "upper": upper.isoformat() if upper else None,
        }
        return json.dumps(payload)

    def from_db_value(self, value, expression, connection):
        if connection.vendor == "postgresql":
            return super().from_db_value(value, expression, connection)
        if value in (None, ""):
            return None
        if isinstance(value, str):
            try:
                payload = json.loads(value)
            except json.JSONDecodeError:
                return value
            lower = payload.get("lower")
            upper = payload.get("upper")
            lower_dt = datetime.fromisoformat(lower) if lower else None
            upper_dt = datetime.fromisoformat(upper) if upper else None
            return (
                timezone.make_aware(lower_dt) if lower_dt and lower_dt.tzinfo is None else lower_dt,
                timezone.make_aware(upper_dt) if upper_dt and upper_dt.tzinfo is None else upper_dt,
            )
        return value

    def get_placeholder(self, value, compiler, connection):
        if connection.vendor != "postgresql":
            return "%s"
        return super().get_placeholder(value, compiler, connection)
