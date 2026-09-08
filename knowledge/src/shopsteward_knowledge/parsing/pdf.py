"""Text-layer extraction with real PDF page numbers; never launches OCR."""

from io import BytesIO

from .models import ParseResult, coverage, locator


def parse_pdf(content: bytes) -> ParseResult:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted and not reader.decrypt(""):
            return ParseResult(
                status="UNSUPPORTED", warnings=["PDF_ENCRYPTED"], coverage=coverage("pages", [])
            )
        blocks, items, warnings = [], [], []
        for number, page in enumerate(reader.pages, 1):
            loc = locator("page", page=number)
            try:
                text = page.extract_text() or ""
                # Image inventory includes nested Form XObjects and inline
                # images without running OCR. Even a page with a text footer
                # can have its entire substantive body in an image.
                has_images = bool(page.images)
            except Exception as exc:
                # One failed page must not discard text extracted on other pages.
                items.append(dict(locator=loc, status="UNPARSED", reason="EXTRACTION_FAILED"))
                warnings.append(f"PDF_PAGE_FAILED:{number}:{type(exc).__name__}")
                continue
            if text.strip():
                blocks.append(dict(text=text.strip(), locator=loc))
                if has_images:
                    items.append(dict(locator=loc, status="PARTIAL", reason="OCR_REQUIRED"))
                    warnings.append(f"PDF_IMAGE_CONTENT:{number}:OCR_REQUIRED")
                else:
                    items.append(dict(locator=loc, status="PARSED"))
            else:
                items.append(dict(locator=loc, status="UNPARSED", reason="OCR_REQUIRED"))
                warnings.append(f"PDF_NO_TEXT_LAYER:{number}:OCR_REQUIRED")
    except (PyPdfError, ValueError, OSError) as exc:
        raise ValueError("invalid PDF original") from exc
    missing = any(i["status"] != "PARSED" for i in items)
    status = "COMPLETE"
    if missing:
        status = (
            "PARTIAL"
            if blocks
            else (
                "OCR_REQUIRED"
                if all(i.get("reason") == "OCR_REQUIRED" for i in items)
                else "UNSUPPORTED"
            )
        )
    return ParseResult(
        status=status, blocks=blocks, warnings=warnings, coverage=coverage("pages", items)
    )
