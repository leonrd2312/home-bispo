import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.main import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def client(db_session):
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def exemplo_nfce() -> dict:
    return json.loads((FIXTURES_DIR / "exemplo_nfce_extraida.json").read_text(encoding="utf-8"))
