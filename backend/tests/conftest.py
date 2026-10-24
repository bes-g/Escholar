import os
import tempfile
from pathlib import Path

_dir = Path(tempfile.mkdtemp(prefix="escholar-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_dir / 'test.db'}"
os.environ["LLM_API_KEY"] = ""
os.environ["LLM_MODEL"] = "test-model"
os.environ["LLM_REASONING_EFFORT"] = ""
os.environ["PINECONE_API_KEY"] = ""
os.environ["PINECONE_INDEX"] = "escholar"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client
