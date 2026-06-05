from __future__ import annotations

import pytest

from src.backend.utility import send


def test_normalize_ms_authority_accepts_plural_and_singular_values() -> None:
    assert send._normalize_ms_authority("organizations") == "organization"
    assert send._normalize_ms_authority("organization") == "organization"
    assert send._normalize_ms_authority("consumers") == "consumer"
    assert send._normalize_ms_authority("consumer") == "consumer"


def test_normalize_ms_authority_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="MS authority must be 'organizations'/'organization' or 'consumers'/'consumer'"):
        send._normalize_ms_authority("other")
