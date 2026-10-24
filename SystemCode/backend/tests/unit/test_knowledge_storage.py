"""Real bounded stream and document checks; no PostgreSQL required."""

import io
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from starlette.requests import Request

from app.core.errors import AppError
from app.knowledge.storage import original_path, receive_upload


def office(extension, *, entries=0, expanded=0, xml=None):
    """Minimal OPC packages with real main-part types and relationships."""
    docx = extension == "docx"
    main = "word/document.xml" if docx else "xl/workbook.xml"
    main_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
        if docx
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
    )
    types = (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'<Override PartName="/{main}" ContentType="{main_type}"/>'
    )
    if not docx:
        types += (
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
    types += "</Types>"
    package = {
        "[Content_Types].xml": types,
        "_rels/.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            'officeDocument" '
            f'Target="{main}"/></Relationships>'
        ),
        main: xml
        or (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>Minimal document</w:t></w:r></w:p></w:body></w:document>"
            if docx
            else '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
    }
    if not docx:
        package["xl/_rels/workbook.xml.rels"] = (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/></Relationships>'
        )
        package["xl/worksheets/sheet1.xml"] = (
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>'
        )
    buf = io.BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as archive:
        for name, data in package.items():
            archive.writestr(name, data)
        for i in range(entries):
            archive.writestr(f"member{i}", b"x")
        if expanded:
            archive.writestr("large", b"x" * expanded)
    return buf.getvalue()


def rewrite_office(data, changes):
    """Corrupt specific package parts while preserving ZIP framing and CRC."""
    out = io.BytesIO()
    with ZipFile(io.BytesIO(data)) as source, ZipFile(out, "w", ZIP_DEFLATED) as target:
        for name in source.namelist():
            content = changes.get(name, source.read(name))
            if content is not None:
                target.writestr(name, content)
    return out.getvalue()


def pdf(*, comment=b"", text=b"Original text"):
    result = b"%PDF-1.7\n" + (b"% " + comment + b"\n" if comment else b"")
    content = b"BT /F1 12 Tf 10 10 Td (" + text + b") Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(result)
    result += b"xref\n0 6\n0000000000 65535 f \n"
    for offset in offsets:
        result += f"{offset:010d} 00000 n \n".encode()
    return result + f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


def request_for(tmp_path, data, *, filename="notes.txt", extra=b"", closed=True):
    prefix = (
        b'--test\r\nContent-Disposition: form-data; name="metadata"\r\n\r\n'
        b'{"title":"Test"}\r\n--test\r\nContent-Disposition: form-data; '
        b'name="file"; filename="' + filename.encode() + b'"\r\n\r\n'
    )
    suffix = b"\r\n" + extra + (b"--test--\r\n" if closed else b"")
    consumed = []

    async def stream():
        yield prefix
        for i in range(0, len(data), 64 * 1024):
            consumed.append(i)
            yield data[i : i + 64 * 1024]
        yield suffix

    iterator = stream().__aiter__()

    async def receive():
        try:
            return {"type": "http.request", "body": await anext(iterator), "more_body": True}
        except StopAsyncIteration:
            return {"type": "http.request", "body": b"", "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [(b"content-type", b"multipart/form-data; boundary=test")],
            "app": SimpleNamespace(
                state=SimpleNamespace(
                    settings=SimpleNamespace(knowledge_storage_root=str(tmp_path))
                )
            ),
        },
        receive=receive,
    )
    return request, consumed


@pytest.mark.parametrize(
    "name,data,mime",
    [
        ("notes.txt", "中文文本".encode(), "text/plain"),
        ("notes.md", b"# Heading", "text/markdown"),
        ("notes.csv", b"sku,price\na,12\n", "text/csv"),
        (
            "notes.docx",
            office("docx"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        (
            "notes.xlsx",
            office("xlsx"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        ("notes.pdf", pdf(), "application/pdf"),
    ],
    ids=["txt", "md", "csv", "docx", "xlsx", "pdf"],
)
async def test_supported_formats_preserve_original_bytes(tmp_path, name, data, mime):
    request, _ = request_for(tmp_path, data, filename=name)
    result = await receive_upload(request)
    assert result.mime_type == mime
    assert (tmp_path / result.raw_key).read_bytes() == data
    assert result.metadata == {"title": "Test"}


async def test_stream_limit_without_content_length_stops_reading_and_removes_partial(tmp_path):
    request, consumed = request_for(tmp_path, b"x" * (22 * 1024 * 1024))
    with pytest.raises(AppError) as failure:
        await receive_upload(request)
    assert failure.value.status == 413
    assert len(consumed) == 321  # rejects first 64 KiB beyond the 20 MiB file limit
    assert not list(tmp_path.iterdir())


async def test_exact_twenty_mib_allowed(tmp_path):
    request, _ = request_for(tmp_path, b"x" * (20 * 1024 * 1024))
    result = await receive_upload(request)
    assert result.size_bytes == 20 * 1024 * 1024


@pytest.mark.parametrize(
    "name,data,extra,closed",
    [
        ("notes.txt", b"text", b"", False),
        (
            "notes.txt",
            b"text",
            b'--test\r\nContent-Disposition: form-data; name="file"; filename="b.txt"\r\n\r\nb\r\n',
            True,
        ),
        ("notes.docx", office("docx", entries=2049), b"", True),
        ("notes.xlsx", office("xlsx", expanded=21 * 1024 * 1024), b"", True),
        (
            "notes.docx",
            office("docx", xml=b'<!DOCTYPE x [<!ENTITY a "x">]><document>&a;</document>'),
            b"",
            True,
        ),
    ],
    ids=["truncated", "two-files", "zip-count", "zip-size", "xml-entity"],
)
async def test_unsafe_streams_or_archives_rejected(tmp_path, name, data, extra, closed):
    request, _ = request_for(tmp_path, data, filename=name, extra=extra, closed=closed)
    with pytest.raises(AppError) as failure:
        await receive_upload(request)
    assert failure.value.status == 422
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("key", ["../secret", "C:/secret", "/etc/passwd", "notes.txt"])
def test_original_key_cannot_choose_a_path(tmp_path, key):
    with pytest.raises(AppError):
        original_path(tmp_path, key)


async def test_bad_zip_payload_returns_validation_error(tmp_path):
    # A ZIP with valid central directory but corrupt compressed bytes must not leak a zlib error.
    data = bytearray(office("docx"))
    name_size = int.from_bytes(data[26:28], "little")
    extra_size = int.from_bytes(data[28:30], "little")
    data[30 + name_size + extra_size] = 0xFF
    request, _ = request_for(tmp_path, bytes(data), filename="notes.docx")
    with pytest.raises(AppError) as failure:
        await receive_upload(request)
    assert failure.value.status == 422


@pytest.mark.parametrize("location", ["comment", "text"])
async def test_unencrypted_pdf_with_encrypt_literal_is_accepted(tmp_path, location):
    data = pdf(**{location: b"/Encrypt"})
    request, _ = request_for(tmp_path, data, filename="literal.pdf")
    result = await receive_upload(request)
    assert (tmp_path / result.raw_key).read_bytes() == data


async def test_pdf_signature_without_objects_or_trailer_is_rejected(tmp_path):
    data = b"%PDF-1.7\nxref\n/Type /Page\nstartxref\n9\n%%EOF\n"
    request, _ = request_for(tmp_path, data, filename="fake.pdf")
    with pytest.raises(AppError) as failure:
        await receive_upload(request)
    assert failure.value.status == 422


@pytest.mark.parametrize(
    "extension,changes",
    [
        ("docx", {"[Content_Types].xml": "<Types/>", "word/document.xml": "<document/>"}),
        ("docx", {"_rels/.rels": None}),
        (
            "docx",
            {
                "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
            },
        ),
        ("docx", {"word/document.xml": "<document><body/></document>"}),
        (
            "docx",
            {
                "word/document.xml": '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'
            },
        ),
        (
            "xlsx",
            {
                "xl/workbook.xml": '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets/></workbook>'
            },
        ),
        ("xlsx", {"xl/_rels/workbook.xml.rels": None}),
        ("xlsx", {"xl/worksheets/sheet1.xml": None}),
        (
            "xlsx",
            {
                "xl/worksheets/sheet1.xml": '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'
            },
        ),
    ],
    ids=[
        "bare-package",
        "no-package-rels",
        "no-main-type",
        "no-main-namespace",
        "no-body",
        "no-sheet",
        "no-sheet-rels",
        "missing-sheet",
        "no-sheet-data",
    ],
)
async def test_incomplete_office_packages_are_rejected(tmp_path, extension, changes):
    data = rewrite_office(office(extension), changes)
    request, _ = request_for(tmp_path, data, filename="bad." + extension)
    with pytest.raises(AppError) as failure:
        await receive_upload(request)
    assert failure.value.status == 422


@pytest.mark.parametrize(
    "old,new",
    [
        (b"word/document.xml", b"word/missing.xml"),
        (
            b'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"',
            b'Type="wrong"',
        ),
        (
            b'Target="word/document.xml"',
            b'Target="https://example.invalid/document.xml" TargetMode="External"',
        ),
    ],
)
async def test_office_main_relationship_must_resolve_to_declared_main_part(tmp_path, old, new):
    data = office("docx")
    with ZipFile(io.BytesIO(data)) as archive:
        rels = archive.read("_rels/.rels").replace(old, new)
    request, _ = request_for(
        tmp_path, rewrite_office(data, {"_rels/.rels": rels}), filename="bad.docx"
    )
    with pytest.raises(AppError) as failure:
        await receive_upload(request)
    assert failure.value.status == 422


async def test_wrong_office_main_content_type_is_rejected(tmp_path):
    data = office("docx")
    with ZipFile(io.BytesIO(data)) as archive:
        types = archive.read("[Content_Types].xml").replace(
            b"document.main+xml", b"template.main+xml"
        )
    request, _ = request_for(
        tmp_path, rewrite_office(data, {"[Content_Types].xml": types}), filename="bad.docx"
    )
    with pytest.raises(AppError) as failure:
        await receive_upload(request)
    assert failure.value.status == 422


async def test_actual_encrypted_pdf_is_rejected(tmp_path):
    from pypdf import PdfWriter

    with PdfWriter() as writer:
        writer.add_blank_page(width=100, height=100)
        writer.encrypt("secret")
        stream = io.BytesIO()
        writer.write(stream)
    request, _ = request_for(tmp_path, stream.getvalue(), filename="encrypted.pdf")
    with pytest.raises(AppError) as failure:
        await receive_upload(request)
    assert failure.value.status == 422


def test_minimal_pdf_fixture_is_readable_text():
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf()), strict=True)
    assert not reader.is_encrypted
    assert len(reader.pages) == 1
    assert reader.pages[0].extract_text() == "Original text"


# These are immutable test inputs generated by K0 with real document libraries.

CORPUS = Path(__file__).resolve().parents[3] / "docs/evaluation/knowledge/sources"
CORPUS_DOCUMENTS = sorted(
    path for path in CORPUS.rglob("*") if path.suffix in {".pdf", ".docx", ".xlsx"}
)


@pytest.mark.parametrize("source", CORPUS_DOCUMENTS, ids=lambda path: path.parent.name)
async def test_readonly_k0_documents_pass_structure_validation(tmp_path, source):
    data = source.read_bytes()
    request, _ = request_for(tmp_path, data, filename=source.name)
    result = await receive_upload(request)
    assert (tmp_path / result.raw_key).read_bytes() == data


CHARTSHEET_BYTES = (
    Path(__file__).resolve().parents[1] / "fixtures/knowledge/chartsheet.xlsx"
).read_bytes()


@pytest.mark.parametrize("wrong_type", [False, True])
async def test_workbook_with_chartsheet_preserves_original_and_checks_part_type(
    tmp_path, wrong_type
):
    data = CHARTSHEET_BYTES
    if wrong_type:
        with ZipFile(io.BytesIO(data)) as archive:
            types = archive.read("[Content_Types].xml").replace(
                b"spreadsheetml.chartsheet+xml", b"spreadsheetml.worksheet+xml"
            )
        data = rewrite_office(data, {"[Content_Types].xml": types})
    request, _ = request_for(tmp_path, data, filename="chartsheet.xlsx")
    if wrong_type:
        with pytest.raises(AppError) as failure:
            await receive_upload(request)
        assert failure.value.status == 422
    else:
        result = await receive_upload(request)
        assert (tmp_path / result.raw_key).read_bytes() == data
