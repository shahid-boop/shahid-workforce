"""Read-only SQL queries against the workforce database.

Statements are validated up front: only a single ``SELECT``/``WITH``/
``EXPLAIN`` statement is allowed, so agents cannot mutate or drop data
through this tool. The session additionally runs in a transaction that is
always rolled back.
"""

from __future__ import annotations

from typing import Any, ClassVar

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from tools.base import BaseTool, ToolError, ToolResult, register, truncate

MAX_ROWS = 200
READ_ONLY_PREFIXES = ("select", "with", "explain", "show", "describe", "pragma")


def validate_read_only(query: str) -> str:
    """Return the normalised query or raise if it is not read-only."""
    cleaned = query.strip().rstrip(";").strip()
    if not cleaned:
        raise ToolError("query is required")
    if ";" in cleaned:
        raise ToolError("only a single statement is allowed")
    first_word = cleaned.split(maxsplit=1)[0].lower()
    if first_word not in READ_ONLY_PREFIXES:
        raise ToolError(
            f"only read-only queries are allowed (got leading {first_word!r})"
        )
    return cleaned


@register
class DatabaseTool(BaseTool):
    """Run one read-only SQL statement and return rows as dicts."""

    name: ClassVar[str] = "database"
    description: ClassVar[str] = (
        "Run a read-only SQL query (SELECT/WITH) against the workforce "
        "database and get rows as dictionaries"
    )

    def __init__(self, engine: Engine | None = None, database_url: str | None = None):
        if engine is not None:
            self._engine = engine
        elif database_url:
            self._engine = create_engine(database_url, future=True)
        else:
            raise ToolError("provide an engine or a database_url")

    def run(
        self, query: str = "", limit: int = MAX_ROWS, **_: Any
    ) -> ToolResult:
        """Execute a read-only query; rows are returned as dicts."""
        cleaned = validate_read_only(query)
        row_limit = max(1, min(int(limit), MAX_ROWS))

        try:
            with self._engine.connect() as connection:
                try:
                    result = connection.execute(text(cleaned))
                    rows = result.mappings().fetchmany(row_limit)
                finally:
                    connection.rollback()  # never commit; read-only by design
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError(f"query failed: {exc}") from exc

        data = [dict(row) for row in rows]
        # Serialize non-JSON-native values (datetimes, UUIDs) as strings.
        serialised = [
            {key: _jsonable(value) for key, value in row.items()} for row in data
        ]
        columns = list(serialised[0]) if serialised else []
        return ToolResult(
            tool=self.name,
            ok=True,
            output=truncate(_render_table(columns, serialised)),
            data={"columns": columns, "rows": serialised, "count": len(serialised)},
        )


def _jsonable(value: Any) -> Any:
    """Convert values that JSON cannot encode into strings."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _render_table(columns: list[str], rows: list[dict[str, Any]]) -> str:
    """Plain-text table for the model context."""
    if not rows:
        return "(no rows)"
    widths = {
        column: max(
            len(column),
            *(len(str(row.get(column, ""))) for row in rows),
        )
        for column in columns
    }
    header = " | ".join(column.ljust(widths[column]) for column in columns)
    rule = "-+-".join("-" * widths[column] for column in columns)
    body = [
        " | ".join(str(row.get(column, "")).ljust(widths[column]) for column in columns)
        for row in rows
    ]
    return "\n".join([header, rule, *body])
