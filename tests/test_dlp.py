"""Tests for backend.security.dlp (mask_pii)."""
from __future__ import annotations

import pytest

from backend.security.dlp import mask_pii


# ---------------------------------------------------------------------------
# test_mask_resident_id (주민번호 마스킹)
# ---------------------------------------------------------------------------


def test_mask_resident_id_basic() -> None:
    """Standard Korean resident registration number is masked."""
    text = "주민번호: 901231-1234567"
    result = mask_pii(text)

    assert "901231-1234567" not in result
    assert "******-*******" in result


def test_mask_resident_id_female_code() -> None:
    """Resident ID starting with digit 2 (female, born pre-2000) is masked."""
    text = "ID: 850615-2123456"
    result = mask_pii(text)

    assert "850615-2123456" not in result
    assert "******-*******" in result


def test_mask_resident_id_new_generation() -> None:
    """Resident ID with digits 3/4 (born 2000+) is masked."""
    text = "주민: 010101-3456789"
    result = mask_pii(text)

    assert "010101-3456789" not in result


# ---------------------------------------------------------------------------
# test_mask_phone (전화번호 마스킹)
# ---------------------------------------------------------------------------


def test_mask_phone_with_dashes() -> None:
    """Korean mobile number with dashes is masked."""
    text = "전화: 010-1234-5678"
    result = mask_pii(text)

    assert "010-1234-5678" not in result
    assert "***-****-****" in result


def test_mask_phone_without_dashes() -> None:
    """Korean mobile number without separators is masked."""
    text = "연락처: 01012345678"
    result = mask_pii(text)

    assert "01012345678" not in result


def test_mask_phone_016_prefix() -> None:
    """Phone numbers with 016 prefix are masked."""
    text = "016-123-4567"
    result = mask_pii(text)

    assert "016-123-4567" not in result


def test_mask_phone_019_prefix() -> None:
    """Phone numbers with 019 prefix are masked."""
    text = "019-9876-5432"
    result = mask_pii(text)

    assert "019-9876-5432" not in result


# ---------------------------------------------------------------------------
# test_mask_card_number (카드번호 마스킹)
# ---------------------------------------------------------------------------


def test_mask_card_number_with_dashes() -> None:
    """16-digit card number separated by dashes is masked."""
    text = "카드: 1234-5678-9012-3456"
    result = mask_pii(text)

    assert "1234-5678-9012-3456" not in result
    assert "****-****-****-****" in result


def test_mask_card_number_without_dashes() -> None:
    """16-digit card number without separators is masked."""
    text = "Card: 1234567890123456"
    result = mask_pii(text)

    assert "1234567890123456" not in result


# ---------------------------------------------------------------------------
# test_mask_email (이메일 마스킹)
# ---------------------------------------------------------------------------


def test_mask_email_simple() -> None:
    """Simple email address is masked."""
    text = "이메일: user@example.com"
    result = mask_pii(text)

    assert "user@example.com" not in result
    assert "***@***.***" in result


def test_mask_email_with_plus() -> None:
    """Email address containing '+' is masked."""
    text = "user+tag@company.co.kr"
    result = mask_pii(text)

    assert "user+tag@company.co.kr" not in result


def test_mask_email_with_subdomain() -> None:
    """Email with subdomain in the domain part is masked."""
    text = "test.user@mail.example.org"
    result = mask_pii(text)

    assert "test.user@mail.example.org" not in result


# ---------------------------------------------------------------------------
# test_no_false_positive
# ---------------------------------------------------------------------------


def test_no_false_positive_plain_sentence() -> None:
    """Ordinary Korean/English text is returned unchanged."""
    text = "안녕하세요. 오늘 날씨가 맑습니다. Hello world."
    result = mask_pii(text)

    assert result == text


def test_no_false_positive_short_number() -> None:
    """A short numeric string that is not PII is not altered."""
    text = "총 3개 항목이 있습니다. 코드: 12345"
    result = mask_pii(text)

    assert result == text


def test_no_false_positive_url() -> None:
    """A plain HTTP URL is not treated as an email address."""
    text = "https://www.example.com/path?query=1"
    result = mask_pii(text)

    # URL itself should not be fully masked (the @ character is absent)
    assert "https://www.example.com" in result


# ---------------------------------------------------------------------------
# test_multiple_pii
# ---------------------------------------------------------------------------


def test_multiple_pii_all_masked() -> None:
    """Multiple PII types in a single string are each masked independently."""
    text = (
        "주민번호: 901231-1234567, "
        "전화: 010-1234-5678, "
        "이메일: admin@corp.com"
    )
    result = mask_pii(text)

    assert "901231-1234567" not in result
    assert "010-1234-5678" not in result
    assert "admin@corp.com" not in result

    assert "******-*******" in result
    assert "***-****-****" in result
    assert "***@***.***" in result


def test_multiple_pii_non_pii_context_preserved() -> None:
    """Non-PII surrounding text is not removed when masking multiple PIIs."""
    text = "연락처: 010-9999-8888. 이름: 홍길동."
    result = mask_pii(text)

    assert "연락처:" in result
    assert "이름: 홍길동" in result


def test_repeated_pii_all_instances_masked() -> None:
    """All occurrences of the same PII type are masked (not just the first)."""
    text = "A: user1@a.com B: user2@b.com"
    result = mask_pii(text)

    assert "user1@a.com" not in result
    assert "user2@b.com" not in result
