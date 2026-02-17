"""Shared test configuration."""

import os

import pytest


@pytest.fixture(autouse=True)
def daktela_env(monkeypatch):
    """Set required Daktela env vars for all tests."""
    monkeypatch.setenv("DAKTELA_URL", "https://test.daktela.com")
    monkeypatch.setenv("DAKTELA_ACCESS_TOKEN", "test-token")
