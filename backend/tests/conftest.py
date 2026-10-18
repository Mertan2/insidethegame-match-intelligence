import pytest

from app.generator import generate_match


@pytest.fixture(scope="session")
def match():
    return generate_match(seed=3, minutes=6)
