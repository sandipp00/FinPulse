import pytest

from backend import auth


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    """The limiters are process-wide; start every test with a clean slate."""
    for limiter in auth.ALL_LIMITERS:
        limiter._hits.clear()
    yield
