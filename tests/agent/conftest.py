import pytest

from tests.agent.test_agent import Clock


@pytest.fixture
def clock() -> Clock:
    return Clock()
