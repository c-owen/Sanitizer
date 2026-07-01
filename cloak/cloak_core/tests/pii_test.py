"""PII detectors — per-type precision/recall and toggling (FR-2)."""

from __future__ import annotations

import pytest

from cloak_core.detectors.pii import (
    PII_TYPES,
    CreditCardDetector,
    EmailDetector,
    IpDetector,
    PhoneDetector,
    SsnDetector,
    UrlDetector,
    pii_detectors,
)


def _values(detector, text):
    return [d.value for d in detector.detect(text)]


# --- email ------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,expected",
    [
        ("write a@b.com please", ["a@b.com"]),
        ("john.doe+tag@sub.example.co.uk", ["john.doe+tag@sub.example.co.uk"]),
    ],
)
def test_email_positive(text, expected):
    assert _values(EmailDetector(), text) == expected


@pytest.mark.parametrize("text", ["no email here", "@nope", "a@b", "foo @ bar.com"])
def test_email_negative(text):
    assert EmailDetector().detect(text) == []


def test_email_metadata():
    det = EmailDetector().detect("A@B.COM")[0]
    assert det.canonical == "a@b.com"  # case-insensitive identity
    assert det.label == "EMAIL"
    assert det.tier.name == "PII"


# --- phone ------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,expected",
    [
        ("call (415) 555-1212 now", ["(415) 555-1212"]),
        ("415-555-1212", ["415-555-1212"]),
        ("415.555.1212", ["415.555.1212"]),
        ("+1 415 555 1212", ["+1 415 555 1212"]),
        ("4155551212", ["4155551212"]),
    ],
)
def test_phone_positive(text, expected):
    assert _values(PhoneDetector(), text) == expected


@pytest.mark.parametrize("text", ["call me", "year 2024", "id 1234", "ab-cd-efgh"])
def test_phone_negative(text):
    assert PhoneDetector().detect(text) == []


def test_phone_same_number_different_formats_share_canonical():
    a = PhoneDetector().detect("(415) 555-1212")[0]
    b = PhoneDetector().detect("415.555.1212")[0]
    assert a.canonical == b.canonical == "4155551212"


# --- credit card (Luhn-validated) -------------------------------------------
@pytest.mark.parametrize(
    "text,digits",
    [
        ("card 4111 1111 1111 1111 ok", "4111111111111111"),
        ("4012888888881881", "4012888888881881"),
        ("378282246310005", "378282246310005"),  # Amex, valid Luhn
    ],
)
def test_credit_card_positive(text, digits):
    dets = CreditCardDetector().detect(text)
    assert len(dets) == 1
    assert dets[0].canonical == digits


@pytest.mark.parametrize(
    "text",
    [
        "4111 1111 1111 1112",  # fails Luhn
        "5555 5555 5555 4443",  # fails Luhn
        "call 415-555-1212",  # only 10 digits
    ],
)
def test_credit_card_negative(text):
    assert CreditCardDetector().detect(text) == []


# --- SSN --------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,expected",
    [("ssn 123-45-6789 ok", ["123-45-6789"]), ("123 45 6789", ["123 45 6789"])],
)
def test_ssn_positive(text, expected):
    assert _values(SsnDetector(), text) == expected


@pytest.mark.parametrize("text", ["123456789", "12-345-6789", "phone 415-555-1212"])
def test_ssn_negative(text):
    assert SsnDetector().detect(text) == []


# --- IP (octet-validated IPv4) ----------------------------------------------
@pytest.mark.parametrize(
    "text,expected",
    [
        ("ip 192.168.0.1 here", ["192.168.0.1"]),
        ("8.8.8.8", ["8.8.8.8"]),
        ("255.255.255.255", ["255.255.255.255"]),
    ],
)
def test_ip_positive(text, expected):
    assert _values(IpDetector(), text) == expected


@pytest.mark.parametrize("text", ["999.999.999.999", "1.2.3", "256.1.1.1"])
def test_ip_negative(text):
    assert IpDetector().detect(text) == []


# --- URL --------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,expected",
    [
        ("see http://example.com now", ["http://example.com"]),
        ("https://sub.example.com/path?q=1", ["https://sub.example.com/path?q=1"]),
        ("go to www.example.com", ["www.example.com"]),
    ],
)
def test_url_positive(text, expected):
    assert _values(UrlDetector(), text) == expected


def test_url_trims_trailing_period():
    assert UrlDetector().detect("visit https://example.com.")[0].value == (
        "https://example.com"
    )


@pytest.mark.parametrize("text", ["just example.com", "ftp://server/file", "no url"])
def test_url_negative(text):
    assert UrlDetector().detect(text) == []


# --- toggling (FR-2) --------------------------------------------------------
def test_default_builds_all_types():
    assert {d.type for d in pii_detectors()} == set(PII_TYPES)


def test_subset_builds_only_requested():
    assert [d.type for d in pii_detectors({"email"})] == ["email"]


def test_unknown_keys_ignored():
    assert pii_detectors({"nope"}) == []
