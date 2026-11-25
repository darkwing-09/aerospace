import os
from unittest.mock import patch
import pytest

from langsmith_service import LangSmithService


def test_zero_egress_blocks_langsmith_client(monkeypatch):
    """Under ZERO_EGRESS_MODE=true, LangSmith client must never be initialized even if a key is provided."""
    monkeypatch.setenv("ZERO_EGRESS_MODE", "true")
    monkeypatch.setenv("AEROMIND_ENV", "prod")
    monkeypatch.setenv("LANGCHAIN_API_KEY", "lsv2_pt_faketestkey123456789")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_pt_faketestkey123456789")

    with patch("langsmith.Client") as mock_client:
        service = LangSmithService()
        assert service.client is None
        mock_client.assert_not_called()
        assert not service.is_cloud_enabled()


def test_dev_mode_allows_langsmith_only_when_zero_egress_disabled(monkeypatch):
    """LangSmith client is only permitted when ZERO_EGRESS_MODE=false AND AEROMIND_ENV=dev AND key is set."""
    monkeypatch.setenv("ZERO_EGRESS_MODE", "false")
    monkeypatch.setenv("AEROMIND_ENV", "dev")
    monkeypatch.setenv("LANGCHAIN_API_KEY", "lsv2_pt_faketestkey123456789")

    with patch("langsmith.Client") as mock_client:
        service = LangSmithService()
        assert service.client is not None
        mock_client.assert_called_once()

