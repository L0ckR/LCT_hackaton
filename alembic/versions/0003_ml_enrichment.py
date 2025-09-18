"""add advanced sentiment fields and widget visualization"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003_ml_enrichment"
down_revision = "0002_email_and_widgets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reviews", sa.Column("sentiment_score", sa.Float(), nullable=True))
    op.add_column("reviews", sa.Column("sentiment_summary", sa.Text(), nullable=True))
    op.add_column("reviews", sa.Column("embedding", sa.JSON(), nullable=True))
    op.add_column("reviews", sa.Column("insights", sa.JSON(), nullable=True))

    op.add_column("widgets", sa.Column("visualization", sa.String(), nullable=True))
    op.execute("UPDATE widgets SET visualization = 'metric' WHERE visualization IS NULL")
    op.alter_column("widgets", "visualization", nullable=False)


def downgrade() -> None:
    op.drop_column("widgets", "visualization")

    op.drop_column("reviews", "insights")
    op.drop_column("reviews", "embedding")
    op.drop_column("reviews", "sentiment_summary")
    op.drop_column("reviews", "sentiment_score")
