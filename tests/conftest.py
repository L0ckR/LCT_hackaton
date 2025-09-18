import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

test_db_path = PROJECT_ROOT / "test.db"
if test_db_path.exists():
    test_db_path.unlink()

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

from app.main import app  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.api.dependencies import get_db  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.models.user import User  # noqa: E402
from app.tasks.sentiment import analyze_sentiment_task  # noqa: E402

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


def _noop_delay(*args, **kwargs):
    return None


analyze_sentiment_task.delay = _noop_delay


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    user = User(email="test@example.com", hashed_password=get_password_hash("test"))
    db.add(user)
    db.commit()
    db.close()
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)
