"""Bounded multipart streaming and original-file validation; no business parsing."""

import codecs
import hashlib
import json
import posixpath
import re
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import uuid4
from xml.parsers import expat
from zipfile import BadZipFile, ZipFile

from pypdf import PdfReader
from pypdf.errors import DependencyError, PyPdfError
from pypdf.generic import ArrayObject, DictionaryObject, StreamObject
from python_multipart import MultipartParser
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header
from starlette.concurrency import run_in_threadpool

from app.core.errors import AppError

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_FORM_BYTES = 64 * 1024
MAX_ZIP_MEMBERS = 2048
MAX_ZIP_BYTES = 100 * 1024 * 1024
MAX_ZIP_MEMBER_BYTES = 20 * 1024 * 1024
MIME = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def invalid(message="Invalid or damaged upload"):
    return AppError(422, "INVALID_UPLOAD", message)


def original_path(root, key):
    if not re.fullmatch(r"[0-9a-f]{32}\.raw", key):
        raise AppError(404, "RESOURCE_NOT_FOUND", "Original does not exist")
    directory = Path(root).resolve()
    path = directory / key
    if path.is_symlink() or path.resolve().parent != directory:
        raise AppError(404, "RESOURCE_NOT_FOUND", "Original does not exist")
    return path


def safe_name(value):
    name = value.replace("\\", "/").rsplit("/", 1)[-1]
    if not name or len(name) > 255 or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise invalid("Invalid filename")
    if Path(name).suffix.lower() not in MIME:
        raise invalid("Supported formats: PDF, DOCX, XLSX, CSV, MD, TXT")
    return name


@dataclass
class XmlInfo:
    root: str = ""
    children: dict = field(default_factory=dict)
    sheets: list = field(default_factory=list)


def validate_xml(content):
    """Validate all XML, retaining only package structure (not document text)."""
    parser = expat.ParserCreate(namespace_separator="}")
    result = XmlInfo()
    stack = []

    def qualified(name):
        return "{" + name if "}" in name else name

    def start(name, attributes):
        name = qualified(name)
        attributes = {qualified(key): value for key, value in attributes.items()}
        if not stack:
            result.root = name
        elif len(stack) == 1:
            result.children.setdefault(name, []).append(attributes)
        elif len(stack) == 2 and stack[1].endswith("}sheets") and name.endswith("}sheet"):
            result.sheets.append((stack[1], name, attributes))
        stack.append(name)

    def end(name):
        stack.pop()

    def forbidden(*args):
        raise invalid("XML DTDs and entities are not supported")

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.StartDoctypeDeclHandler = forbidden
    parser.EntityDeclHandler = forbidden
    parser.ExternalEntityRefHandler = forbidden
    parser.Parse(content, True)
    return result


PACKAGE_TYPES = "{http://schemas.openxmlformats.org/package/2006/content-types}"
PACKAGE_RELS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
OFFICE_RELS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/",
    "http://purl.oclc.org/ooxml/officeDocument/relationships/",
)
WORD_NS = (
    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}",
    "{http://purl.oclc.org/ooxml/wordprocessingml/main}",
)
SHEET_NS = (
    "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}",
    "{http://purl.oclc.org/ooxml/spreadsheetml/main}",
)


def relationship_part(target, source=""):
    uri = urlsplit(target)
    if not target or uri.scheme or uri.netloc or uri.query or uri.fragment:
        raise invalid("Office relationship requires an internal part")
    target = unquote(uri.path, errors="strict")
    if "\\" in target or ":" in target or "\x00" in target:
        raise invalid("Invalid Office relationship target")
    name = posixpath.normpath(
        target.lstrip("/")
        if target.startswith("/")
        else posixpath.join(posixpath.dirname(source), target)
    )
    if name in {".", ".."} or name.startswith("../"):
        raise invalid("Office relationship escapes the package")
    return name


def relationships(info):
    if info.root != PACKAGE_RELS + "Relationships":
        raise invalid("Incorrect Office relationships namespace")
    result = {}
    for attributes in info.children.get(PACKAGE_RELS + "Relationship", []):
        identifier = attributes.get("Id")
        if (
            not identifier
            or identifier in result
            or not attributes.get("Type")
            or not attributes.get("Target")
        ):
            raise invalid("Invalid or duplicate Office relationship")
        result[identifier] = attributes
    return result


def validate_office(archive, infos, extension):
    names = set(archive.namelist())

    def xml(name):
        if name not in names:
            raise invalid("Office document part is missing")
        if name not in infos:
            infos[name] = validate_xml(archive.read(name))
        return infos[name]

    types = xml("[Content_Types].xml")
    if types.root != PACKAGE_TYPES + "Types":
        raise invalid("Incorrect Office content-types namespace")
    overrides, defaults = {}, {}
    for item in types.children.get(PACKAGE_TYPES + "Override", []):
        name = item.get("PartName", "")
        if not name.startswith("/") or not item.get("ContentType"):
            raise invalid("Invalid Office content-type declaration")
        name = relationship_part(name)
        if name in overrides:
            raise invalid("Duplicate Office content-type declaration")
        overrides[name] = item["ContentType"]
    for item in types.children.get(PACKAGE_TYPES + "Default", []):
        ext = item.get("Extension", "")
        if not ext or ext in defaults or not item.get("ContentType"):
            raise invalid("Invalid Office default content type")
        defaults[ext] = item["ContentType"]

    def content_type(name):
        return overrides.get(name, defaults.get(name.rsplit(".", 1)[-1]))

    package = relationships(xml("_rels/.rels"))
    main_links = [
        item
        for item in package.values()
        if item["Type"] in {prefix + "officeDocument" for prefix in OFFICE_RELS}
    ]
    if len(main_links) != 1 or main_links[0].get("TargetMode", "Internal") != "Internal":
        raise invalid("Office package requires one internal officeDocument relationship")
    main = relationship_part(main_links[0]["Target"])
    info = xml(main)
    main_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
        if extension == ".docx"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
    )
    if content_type(main) != main_type:
        raise invalid("Office main content type does not match the file format")
    if extension == ".docx":
        namespaces = [ns for ns in WORD_NS if info.root == ns + "document"]
        if not namespaces or len(info.children.get(namespaces[0] + "body", [])) != 1:
            raise invalid("DOCX requires a namespaced document and body")
        return
    namespaces = [ns for ns in SHEET_NS if info.root == ns + "workbook"]
    if not namespaces or len(info.children.get(namespaces[0] + "sheets", [])) != 1:
        raise invalid("XLSX requires a namespaced workbook and sheets")
    ns = namespaces[0]
    sheet_entries = [
        attributes
        for parent, tag, attributes in info.sheets
        if parent == ns + "sheets" and tag == ns + "sheet"
    ]
    if not sheet_entries:
        raise invalid("XLSX requires at least one sheet")
    rels_name = posixpath.join(posixpath.dirname(main), "_rels", posixpath.basename(main) + ".rels")
    workbook_rels = relationships(xml(rels_name))
    seen_ids, seen_names, seen_links = set(), set(), set()
    for sheet in sheet_entries:
        sheet_id, name = sheet.get("sheetId", ""), sheet.get("name", "")
        link = next(
            (
                sheet.get("{" + prefix.rstrip("/") + "}id")
                for prefix in OFFICE_RELS
                if sheet.get("{" + prefix.rstrip("/") + "}id")
            ),
            None,
        )
        if (
            not sheet_id.isdecimal()
            or int(sheet_id) < 1
            or not name
            or not link
            or sheet_id in seen_ids
            or name in seen_names
            or link in seen_links
        ):
            raise invalid("Invalid or duplicate XLSX sheet identity")
        seen_ids.add(sheet_id)
        seen_names.add(name)
        seen_links.add(link)
        relation = workbook_rels.get(link)
        sheet_kind = next(
            (
                kind
                for kind in ("worksheet", "chartsheet", "dialogsheet")
                if relation and relation["Type"] in {prefix + kind for prefix in OFFICE_RELS}
            ),
            None,
        )
        if (
            not relation
            or relation.get("TargetMode", "Internal") != "Internal"
            or sheet_kind is None
        ):
            raise invalid("XLSX sheet requires a supported internal sheet relationship")
        part = relationship_part(relation["Target"], main)
        worksheet = xml(part)
        if (
            content_type(part)
            != f"application/vnd.openxmlformats-officedocument.spreadsheetml.{sheet_kind}+xml"
            or worksheet.root != ns + sheet_kind
            or (
                sheet_kind == "worksheet" and len(worksheet.children.get(ns + "sheetData", [])) != 1
            )
        ):
            raise invalid("XLSX requires correctly typed sheet parts; worksheets need sheetData")


def validate_pdf(path):
    try:
        with path.open("rb") as source:
            reader = PdfReader(source, strict=True)
            if reader.is_encrypted:
                raise invalid("Encrypted PDFs are not supported")
            root = reader.trailer["/Root"].get_object()
            if not isinstance(root, DictionaryObject) or root.get("/Type") != "/Catalog":
                raise invalid("PDF requires a catalog")
            pages = root["/Pages"].get_object()
            if not isinstance(pages, DictionaryObject) or pages.get("/Type") != "/Pages":
                raise invalid("PDF requires a page tree")
            count = len(reader.pages)
            if count < 1 or pages.get("/Count") != count:
                raise invalid("Invalid PDF page count")
            for page in reader.pages:
                if page.get("/Type") != "/Page" or len(page.mediabox) != 4:
                    raise invalid("Invalid PDF page structure")
                contents = page.get("/Contents")
                if contents is not None:
                    contents = contents.get_object()
                    streams = contents if isinstance(contents, ArrayObject) else [contents]
                    if any(not isinstance(stream.get_object(), StreamObject) for stream in streams):
                        raise invalid("Invalid PDF page content reference")
    except (
        PyPdfError,
        DependencyError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
        OverflowError,
        RecursionError,
    ) as exc:
        raise invalid("Damaged or encrypted PDF") from exc


def validate_file(path, name):
    extension = Path(name).suffix.lower()
    try:
        if extension in {".txt", ".md", ".csv"}:
            decoder = codecs.getincrementaldecoder("utf-8")("strict")
            with path.open("rb") as source:
                while chunk := source.read(64 * 1024):
                    value = decoder.decode(chunk)
                    if any(ord(c) < 32 and c not in "\t\n\r\f" for c in value):
                        raise invalid("Text must contain valid UTF-8 without binary controls")
                decoder.decode(b"", final=True)
        elif extension == ".pdf":
            validate_pdf(path)
        else:
            with path.open("rb") as source:
                signature = source.read(4)
            if signature != b"PK\x03\x04":
                raise invalid("Invalid Office ZIP signature")
            with ZipFile(path) as archive:
                members = archive.infolist()
                if (
                    len(members) > MAX_ZIP_MEMBERS
                    or sum(m.file_size for m in members) > MAX_ZIP_BYTES
                    or any(m.file_size > MAX_ZIP_MEMBER_BYTES for m in members)
                ):
                    raise invalid("Office archive exceeds expansion limits")
                names = {m.filename for m in members}
                if len(names) != len(members):
                    raise invalid("Duplicate Office ZIP members")
                roots = {}
                for member in members:
                    parts = member.filename.replace("\\", "/").split("/")
                    if (
                        member.flag_bits & 1
                        or ".." in parts
                        or member.filename.startswith(("/", "\\"))
                        or ":" in member.filename
                        or "vba" in member.filename.lower()
                    ):
                        raise invalid("Unsafe or encrypted Office member")
                    # Read every member: verifies CRC and the declared expansion budget.
                    with archive.open(member) as source:
                        content = source.read(MAX_ZIP_MEMBER_BYTES + 1)
                    if len(content) > MAX_ZIP_MEMBER_BYTES:
                        raise invalid("Office member exceeds expansion limit")
                    if member.filename.endswith((".xml", ".rels")):
                        roots[member.filename] = validate_xml(content)
                validate_office(archive, roots, extension)
    except (
        UnicodeError,
        BadZipFile,
        expat.ExpatError,
        RuntimeError,
        NotImplementedError,
        EOFError,
        ValueError,
        zlib.error,
    ) as exc:
        raise invalid() from exc
    return MIME[extension]


@dataclass
class StoredUpload:
    raw_key: str
    original_name: str
    content_sha256: str
    size_bytes: int
    mime_type: str
    metadata: dict


class MultipartUpload:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.key = uuid4().hex + ".raw"
        self.path = original_path(self.root, self.key)
        self.file = None
        self.name = None
        self.size = 0
        self.sha = hashlib.sha256()
        self.metadata = bytearray()
        self.parts = set()
        self.complete = False
        self.header_size = 0

    def on_part_begin(self):
        self.headers = {}
        self.field = bytearray()
        self.value = bytearray()
        self.part = None

    def on_header_field(self, data, start, end):
        self.header_size += end - start
        if self.header_size > MAX_FORM_BYTES:
            raise invalid("Multipart headers too large")
        self.field.extend(data[start:end])

    def on_header_value(self, data, start, end):
        self.header_size += end - start
        if self.header_size > MAX_FORM_BYTES:
            raise invalid("Multipart headers too large")
        self.value.extend(data[start:end])

    def on_header_end(self):
        key = bytes(self.field).lower()
        if key in self.headers:
            raise invalid("Duplicate multipart header")
        self.headers[key] = bytes(self.value)
        self.field.clear()
        self.value.clear()

    def on_headers_finished(self):
        disposition, options = parse_options_header(self.headers.get(b"content-disposition", b""))
        name = options.get(b"name")
        if disposition != b"form-data" or name not in {b"file", b"metadata"} or name in self.parts:
            raise invalid("Send exactly one file and one metadata field")
        self.parts.add(name)
        self.part = name
        if name == b"file":
            try:
                self.name = safe_name(options[b"filename"].decode("utf-8"))
            except (KeyError, UnicodeError) as exc:
                raise invalid("File requires a UTF-8 filename") from exc
            self.root.mkdir(parents=True, exist_ok=True)
            self.file = self.path.open("xb")
        elif b"filename" in options:
            raise invalid("Metadata must be a JSON text field")

    def on_part_data(self, data, start, end):
        chunk = data[start:end]
        if self.part == b"file":
            self.size += len(chunk)
            if self.size > MAX_FILE_BYTES:
                raise AppError(413, "UPLOAD_TOO_LARGE", "File exceeds 20 MiB")
            self.sha.update(chunk)
            self.file.write(chunk)
        elif self.part == b"metadata":
            if len(self.metadata) + len(chunk) > MAX_FORM_BYTES:
                raise invalid("Metadata exceeds 64 KiB")
            self.metadata.extend(chunk)

    def on_end(self):
        self.complete = True

    def finish(self):
        if self.file:
            self.file.close()
        if not self.complete or self.parts != {b"file", b"metadata"} or self.size == 0:
            raise invalid("Incomplete multipart upload or empty file")
        try:
            metadata = json.loads(self.metadata)
            if not isinstance(metadata, dict):
                raise ValueError()
        except (ValueError, UnicodeError) as exc:
            raise invalid("Metadata must be a JSON object") from exc
        mime = validate_file(self.path, self.name)
        return StoredUpload(self.key, self.name, self.sha.hexdigest(), self.size, mime, metadata)

    def discard(self):
        if self.file:
            self.file.close()
            # Only this request's unique, exclusively-created file may be removed.
            self.path.unlink(missing_ok=True)


async def receive_upload(request):
    content_type, options = parse_options_header(request.headers.get("content-type", ""))
    boundary = options.get(b"boundary", b"")
    if content_type != b"multipart/form-data" or not 1 <= len(boundary) <= 200:
        raise invalid("Expected multipart/form-data with a boundary")
    upload = MultipartUpload(request.app.state.settings.knowledge_storage_root)
    callbacks = {
        name: getattr(upload, name)
        for name in (
            "on_part_begin",
            "on_header_field",
            "on_header_value",
            "on_header_end",
            "on_headers_finished",
            "on_part_data",
            "on_end",
        )
    }
    parser = MultipartParser(boundary, callbacks)
    total = 0
    try:
        async for chunk in request.stream():
            total += len(chunk)
            if total > MAX_FILE_BYTES + 2 * MAX_FORM_BYTES:
                raise AppError(413, "UPLOAD_TOO_LARGE", "Multipart body exceeds upload limit")
            await run_in_threadpool(parser.write, chunk)
        await run_in_threadpool(parser.finalize)
        return await run_in_threadpool(upload.finish)
    except BaseException as exc:
        await run_in_threadpool(upload.discard)
        if isinstance(exc, MultipartParseError):
            raise invalid("Malformed multipart body") from exc
        raise
