import os

import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url


@pytest_asyncio.fixture
async def db():
    from app.db.session import Database

    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to the dedicated PostgreSQL test database")
    assert make_url(url).database == "shopsteward_test"
    database = Database(url)
    assert await database.ready(), "Apply migrations to the test database"
    yield database
    await database.dispose()
