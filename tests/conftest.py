"""Shared test fixtures."""

import os
import pytest

# Force mock mode for all tests
os.environ["LLM_PROVIDER"] = "mock"
os.environ["VISION_PROVIDER"] = "mock"
os.environ["EXA_API_KEY"] = ""
os.environ["GOOGLE_MAPS_API_KEY"] = ""


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset config and DB singletons between tests."""
    import app.config as config_module
    import app.storage.database as db_module
    config_module._settings = None
    db_module._db = None
    yield
    config_module._settings = None
    db_module._db = None
