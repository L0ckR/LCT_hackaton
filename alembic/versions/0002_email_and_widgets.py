"""swap username for email and add widgets table"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002_email_and_widgets"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index("ix_users_username")
        batch_op.alter_column(
            "username",
            existing_type=sa.String(),
            nullable=False,
            new_column_name="email",
        )
        batch_op.create_index("ix_users_email", ["email"], unique=False)

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.table_constraints
                WHERE constraint_name = 'users_username_key'
                  AND table_name = 'users'
            ) THEN
                ALTER TABLE users RENAME CONSTRAINT users_username_key TO users_email_key;
            END IF;
        END$$;
        """
    )

    op.create_table(
        "widgets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
    )
    op.create_index("ix_widgets_owner_id", "widgets", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_widgets_owner_id", table_name="widgets")
    op.drop_table("widgets")

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.table_constraints
                WHERE constraint_name = 'users_email_key'
                  AND table_name = 'users'
            ) THEN
                ALTER TABLE users RENAME CONSTRAINT users_email_key TO users_username_key;
            END IF;
        END$$;
        """
    )

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index("ix_users_email")
        batch_op.alter_column(
            "email",
            existing_type=sa.String(),
            nullable=False,
            new_column_name="username",
        )
        batch_op.create_index("ix_users_username", ["username"], unique=False)
