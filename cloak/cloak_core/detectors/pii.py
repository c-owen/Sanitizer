"""Structured-PII detection — rule-based, fast, auditable (FR-2).

Each PII type is an independent, individually toggleable :class:`Detector`.
Detection leans toward *recall* (the brief's R1: a missed item is the
catastrophic failure), so some patterns intentionally over-match; the
verification gate re-checks the output and the review surface lets the user
reject false positives. Every detector documents its posture below.

Types (stable toggle keys): ``email``, ``phone``, ``credit_card``, ``ssn``,
``ip``, ``url``. Disabled types are never matched, so their text is left
untouched (FR-2).
"""

from __future__ import annotations

import re

from cloak_core.model import Detection, Span, TrustTier


class _RegexDetector:
    """Shared machinery: find matches, optionally refine span, validate and
    canonicalize. Subclasses set ``type``, ``label``, ``reason`` and ``pattern``.
    """

    type: str
    label: str
    reason: str
    pattern: re.Pattern[str]

    def detect(self, text: str) -> list[Detection]:
        results: list[Detection] = []
        for match in self.pattern.finditer(text):
            value, start, end = self._refine(match)
            if not value or not self._is_valid(value):
                continue
            results.append(
                Detection(
                    span=Span(start, end),
                    value=value,
                    type=self.type,
                    label=self.label,
                    tier=TrustTier.PII,
                    reason=self.reason,
                    canonical=self._canonical(value),
                    restore=value,
                )
            )
        return results

    def _refine(self, match: re.Match[str]) -> tuple[str, int, int]:
        return match.group(), match.start(), match.end()

    def _is_valid(self, value: str) -> bool:
        return True

    def _canonical(self, value: str) -> str:
        return value


class EmailDetector(_RegexDetector):
    """Email addresses. Posture: standard pattern; case-insensitive identity."""

    type = "email"
    label = "EMAIL"
    reason = "email pattern"
    pattern = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

    def _canonical(self, value: str) -> str:
        return value.casefold()


class PhoneDetector(_RegexDetector):
    """Phone numbers (US-style 3-3-4, optional country code and separators).

    Posture: recall-leaning and US-centric; a bare 10-digit run matches, so it
    can over-match numeric IDs. The same number in different formats shares one
    placeholder (canonical = digits only). International formats are roadmap.
    """

    type = "phone"
    label = "PHONE"
    reason = "phone pattern"
    pattern = re.compile(
        r"(?<!\d)"  # not inside a longer digit run
        r"(?:\+?\d{1,2}[\s.-]?)?"  # optional country code
        r"\(?\d{3}\)?[\s.-]?"  # area code
        r"\d{3}[\s.-]?\d{4}"  # prefix + line
        r"(?!\d)"
    )

    def _canonical(self, value: str) -> str:
        return re.sub(r"\D", "", value)


class CreditCardDetector(_RegexDetector):
    """Credit-card numbers (13–19 digits, optional space/dash groups).

    Posture: precise — a Luhn checksum filters out random digit runs, so false
    positives are rare without hurting recall on real cards. Canonical = digits.
    """

    type = "credit_card"
    label = "CARD"
    reason = "credit-card pattern"
    # Either 13–19 contiguous digits, or 4-digit groups joined by ONE consistent
    # separator (the ``\1`` backreference). Requiring a consistent grouping stops
    # the match from bridging an adjacent, differently-grouped number such as an
    # SSN ("123-45-6789 4111 1111 …"). Luhn (below) filters the rest.
    pattern = re.compile(
        r"(?<![\d-])"
        r"(?:\d{4}([ -])\d{4}\1\d{4}\1\d{1,7}|\d{13,19})"
        r"(?![\d])"
    )

    def _is_valid(self, value: str) -> bool:
        return _luhn_ok(re.sub(r"\D", "", value))

    def _canonical(self, value: str) -> str:
        return re.sub(r"\D", "", value)


class SsnDetector(_RegexDetector):
    """US Social Security numbers in the dashed/spaced form ``DDD-DD-DDDD``.

    Posture: precise — requires separators, so it won't match arbitrary 9-digit
    runs (a precision/recall trade chosen to avoid mass false positives).
    """

    type = "ssn"
    label = "SSN"
    reason = "SSN pattern"
    pattern = re.compile(r"(?<!\d)\d{3}[-\s]\d{2}[-\s]\d{4}(?!\d)")

    def _canonical(self, value: str) -> str:
        return re.sub(r"\D", "", value)


class IpDetector(_RegexDetector):
    """IPv4 addresses with validated octets (0–255). IPv6 is roadmap."""

    type = "ip"
    label = "IP"
    reason = "IP address pattern"
    _octet = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
    pattern = re.compile(rf"(?<![\d.])(?:{_octet}\.){{3}}{_octet}(?![\d.])")


class UrlDetector(_RegexDetector):
    """URLs (``http(s)://…`` or ``www.…``). Trailing sentence punctuation is
    trimmed so "see http://x.com." doesn't capture the period."""

    type = "url"
    label = "URL"
    reason = "URL pattern"
    pattern = re.compile(r"\b(?:https?://|www\.)[^\s<>\"')\]]+", re.IGNORECASE)
    _TRAILING = ".,;:!?"

    def _refine(self, match: re.Match[str]) -> tuple[str, int, int]:
        value, start, end = match.group(), match.start(), match.end()
        while value and value[-1] in self._TRAILING:
            value, end = value[:-1], end - 1
        return value, start, end


def _luhn_ok(digits: str) -> bool:
    """Luhn checksum — True if ``digits`` is a valid card-style number."""
    if not digits.isdigit() or not 13 <= len(digits) <= 19:
        return False
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


# Registry — order is the stable display/placeholder order.
_DETECTOR_CLASSES: dict[str, type[_RegexDetector]] = {
    "email": EmailDetector,
    "phone": PhoneDetector,
    "credit_card": CreditCardDetector,
    "ssn": SsnDetector,
    "ip": IpDetector,
    "url": UrlDetector,
}

PII_TYPES: tuple[str, ...] = tuple(_DETECTOR_CLASSES)


def pii_detectors(enabled: set[str] | None = None) -> list[_RegexDetector]:
    """Build the enabled PII detectors (default: all).

    Disabled types are simply absent, so their text is never touched (FR-2).
    Unknown keys are ignored.
    """
    selected = set(PII_TYPES) if enabled is None else set(enabled)
    return [cls() for key, cls in _DETECTOR_CLASSES.items() if key in selected]
