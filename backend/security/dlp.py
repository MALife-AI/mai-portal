"""DLP & PII Masking Middleware."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Literal

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse


# Masking level type
MaskingLevel = Literal["full", "partial", "hash"]

# Default masking level (can be overridden per call)
DEFAULT_MASKING_LEVEL: MaskingLevel = "full"

# Paths to skip DLP scanning for performance
DLP_SKIP_PATHS: set[str] = {"/health", "/docs", "/openapi.json", "/redoc"}

PII_PATTERNS = {
    "resident_id": (re.compile(r"\d{6}-[1-4]\d{6}"), "******-*******"),
    "phone": (re.compile(r"01[016789]-?\d{3,4}-?\d{4}"), "***-****-****"),
    "card_number": (re.compile(r"\d{4}-?\d{4}-?\d{4}-?\d{4}"), "****-****-****-****"),
    "email": (re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"), "***@***.***"),
    # Korean-specific PII patterns
    "business_registration_number": (
        re.compile(r"\d{3}-\d{2}-\d{5}"),
        "***-**-*****",
    ),  # 사업자등록번호
    "passport_number": (
        re.compile(r"[A-Z]{1,2}\d{7,8}"),
        "**********",
    ),  # 여권번호
    "driver_license_number": (
        re.compile(r"\d{2}-\d{2}-\d{6}-\d{2}"),
        "**-**-******-**",
    ),  # 운전면허번호
    "bank_account_number": (
        re.compile(
            r"(?:"
            r"\d{3}-\d{2}-\d{6}"        # 국민은행 등 (3-2-6)
            r"|\d{3}-\d{6}-\d{2}-\d{3}"  # 우리은행 등 (3-6-2-3)
            r"|\d{4}-\d{4}-\d{4}"        # 신한은행 등 (4-4-4)
            r"|\d{3}-\d{4}-\d{4}-\d{2}"  # 하나은행 등 (3-4-4-2)
            r")"
        ),
        "****-****-****",
    ),  # 계좌번호
}


def _apply_masking(original: str, pii_type: str, level: MaskingLevel = "full") -> str:
    """Apply masking based on the configured masking level."""
    if level == "full":
        _, replacement = PII_PATTERNS[pii_type]
        return replacement
    elif level == "partial":
        if len(original) <= 4:
            return "*" * len(original)
        return "*" * (len(original) - 4) + original[-4:]
    elif level == "hash":
        return hashlib.sha256(original.encode("utf-8")).hexdigest()
    return original


@dataclass
class PIIFinding:
    """Single PII finding in scanned content."""
    pii_type: str
    start: int
    end: int
    masked_value: str
    original_length: int


@dataclass
class PiiScanReport:
    """Summary report of all PII findings from a scan."""
    total_findings: int = 0
    findings_by_type: dict[str, int] = field(default_factory=dict)
    findings: list[PIIFinding] = field(default_factory=list)
    scanned_length: int = 0

    @property
    def has_pii(self) -> bool:
        return self.total_findings > 0


def scan_file_content(
    content: str,
    masking_level: MaskingLevel = "full",
) -> list[dict]:
    """Scan content for all PII occurrences.

    Returns a list of dicts with type, position, and masked value for each finding.
    """
    findings: list[dict] = []
    for pii_type, (pattern, _replacement) in PII_PATTERNS.items():
        for match in pattern.finditer(content):
            masked = _apply_masking(match.group(), pii_type, masking_level)
            findings.append(
                {
                    "type": pii_type,
                    "start": match.start(),
                    "end": match.end(),
                    "masked_value": masked,
                    "original_length": len(match.group()),
                }
            )
    findings.sort(key=lambda f: f["start"])
    return findings


def generate_scan_report(
    content: str,
    masking_level: MaskingLevel = "full",
) -> PiiScanReport:
    """Generate a structured PII scan report from content."""
    raw_findings = scan_file_content(content, masking_level)
    report = PiiScanReport(scanned_length=len(content))
    for f in raw_findings:
        finding = PIIFinding(
            pii_type=f["type"],
            start=f["start"],
            end=f["end"],
            masked_value=f["masked_value"],
            original_length=f["original_length"],
        )
        report.findings.append(finding)
        report.findings_by_type[f["type"]] = report.findings_by_type.get(f["type"], 0) + 1
    report.total_findings = len(raw_findings)
    return report


def mask_pii(text: str, masking_level: MaskingLevel = "full") -> str:
    """Mask all PII in text using the specified masking level."""
    for pii_type, (pattern, _replacement) in PII_PATTERNS.items():
        text = pattern.sub(
            lambda m, pt=pii_type: _apply_masking(m.group(), pt, masking_level),
            text,
        )
    return text


class DLPMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, skip_paths: set[str] | None = None):
        super().__init__(app)
        self.skip_paths = skip_paths or DLP_SKIP_PATHS

    async def dispatch(self, request: Request, call_next):
        # Skip DLP scanning for configured paths (performance optimization)
        if request.url.path in self.skip_paths:
            return await call_next(request)

        response = await call_next(request)

        # Extract body from both StreamingResponse and regular Response
        if isinstance(response, StreamingResponse):
            original_body = b""
            async for chunk in response.body_iterator:
                if isinstance(chunk, str):
                    chunk = chunk.encode()
                original_body += chunk
        elif hasattr(response, "body"):
            original_body = response.body
        else:
            return response

        content_type = response.headers.get("content-type", "")
        if "text" not in content_type and "json" not in content_type:
            return Response(
                content=original_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        masked = mask_pii(original_body.decode("utf-8", errors="replace"))
        return Response(
            content=masked,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
