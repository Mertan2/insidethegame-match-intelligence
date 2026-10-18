import pytest

from app.generator import generate_match


@pytest.fixture(scope="session")
def match():
    return generate_match(seed=3, minutes=6)


@pytest.fixture(scope="session")
def long_match():
    """Enough play for rarer moments (headed attempts, on-target forecasts)."""
    return generate_match(seed=11, minutes=20)
