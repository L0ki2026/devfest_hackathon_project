import os

import pytest

# Force offline demo before app imports in test modules
os.environ["DEMO_MODE"] = "true"
os.environ.pop("FDC_API_KEY", None)
os.environ.pop("GEMINI_API_KEY", None)


@pytest.fixture(autouse=True)
def reset_settings_cache():
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c