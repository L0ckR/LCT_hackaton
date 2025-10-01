"""Enable TimescaleDB hypertables and pgvector embeddings."""

from alembic import context, op
import sqlalchemy as sa


revision = "0004_timescale_pgvector"
down_revision = "0003_ml_enrichment"
branch_labels = None
depends_on = None


def _log_warning(message: str) -> None:
    ctx = context.get_context()
    logger = getattr(ctx, "log", None)
    if logger is not None:
        logger.warning(message)
    else:  # pragma: no cover - fallback for direct execution
        print(message)


def _get_column_type(connection, table: str, column: str) -> str | None:
    query = sa.text(
        """
        SELECT atttypid::regtype::text
        FROM pg_attribute
        JOIN pg_class ON pg_class.oid = pg_attribute.attrelid
        JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
        WHERE pg_namespace.nspname = current_schema()
          AND pg_class.relname = :table
          AND pg_attribute.attname = :column
          AND pg_attribute.attnum > 0
          AND NOT pg_attribute.attisdropped
        """
    )
    return connection.execute(query, {"table": table, "column": column}).scalar()


def _ensure_extension(connection, name: str) -> bool:
    available = connection.execute(
        sa.text("SELECT 1 FROM pg_available_extensions WHERE name = :name"),
        {"name": name},
    ).scalar()
    if not available:
        _log_warning(
            f"Extension '{name}' is not available; skipping related migration steps"
        )
        return False

    try:
        connection.execute(sa.text(f"CREATE EXTENSION IF NOT EXISTS {name}"))
    except sa.exc.DBAPIError as exc:  # pragma: no cover - defensive
        _log_warning(
            f"Failed to create extension '{name}'; skipping related migration steps ({exc})"
        )
        return False
    return True


def _type_exists(connection, type_name: str) -> bool:
    return bool(
        connection.execute(
            sa.text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = :name)"),
            {"name": type_name},
        ).scalar()
    )


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        return

    has_timescale = _ensure_extension(connection, "timescaledb")
    has_vector = _ensure_extension(connection, "vector")

    if has_vector and _type_exists(connection, "vector"):
        current_type = _get_column_type(connection, "reviews", "embedding")
        if current_type != "vector":
            connection.execute(
                sa.text(
                    "ALTER TABLE reviews ALTER COLUMN embedding TYPE vector USING (embedding::text)::vector"
                )
            )
    elif has_vector:
        _log_warning("pgvector extension is present but vector type is unavailable; leaving column as JSON")

    if has_timescale:
        connection.execute(
            sa.text(
                "SELECT create_hypertable('reviews', 'date', if_not_exists => TRUE, migrate_data => TRUE)"
            )
        )
        connection.execute(
            sa.text(
                "SELECT add_dimension('reviews', 'product', if_not_exists => TRUE)"
            )
        )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        return

    current_type = _get_column_type(connection, "reviews", "embedding")
    if current_type == "vector":
        connection.execute(
            sa.text(
                "ALTER TABLE reviews ALTER COLUMN embedding TYPE json USING to_json(embedding::float8[])"
            )
        )

    connection.execute(
        sa.text("SELECT remove_hypertable(current_schema(), 'reviews', if_exists => TRUE)")
    )
