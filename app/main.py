from fastapi import FastAPI

from app.api.routes import auth, reviews
from app.db.base import Base
from app.db.session import engine

# Create tables for demo purposes (use Alembic for real migrations)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Review Analytics Service")

app.include_router(auth.router)
app.include_router(reviews.router)
