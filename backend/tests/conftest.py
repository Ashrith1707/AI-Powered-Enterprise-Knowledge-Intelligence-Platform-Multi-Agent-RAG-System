"""Test fixtures: in-memory SQLite + authenticated FastAPI TestClient."""
import os

# Must be set BEFORE any app import: keeps tests off the real database/LLM
# regardless of what backend/.env contains.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["GEMINI_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.core.database import Base, get_db
from app.main import app

engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                       poolclass=StaticPool)
TestSession = sessionmaker(bind=engine)

TEST_USER = {"email": "tester@corp.com", "password": "S3curePass!", "full_name": "Test User"}


@pytest.fixture()
def db():
    Base.metadata.create_all(engine)
    session = TestSession()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture()
def anon_client(db):
    """Client with the DB override but NO auth header."""
    def override_get_db():
        yield db

    main_module._rate_buckets.clear()  # rate limits must not leak across tests
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def client(anon_client):
    """Authenticated client — registers a fresh user and attaches the JWT."""
    res = anon_client.post("/api/auth/register", json=TEST_USER)
    assert res.status_code == 201, res.text
    token = res.json()["access_token"]
    anon_client.headers["Authorization"] = f"Bearer {token}"
    anon_client.tokens = res.json()
    yield anon_client
