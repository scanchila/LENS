"""LENS-local conftest.

The PR 4 part 1 tests (template renderer + gather_evidence script) do not
require the FastAPI/Postgres backend stack from the parent ``tests/conftest.py``.
We override the autouse ``db`` fixture here so these tests don't pull in the
backend's Postgres dependency.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session", autouse=True)
def db():
    """No-op override of the parent backend ``db`` fixture for LENS unit tests."""
    yield None
