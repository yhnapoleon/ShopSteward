from openapi_spec_validator import validate

from app.core.config import Settings
from app.main import create_app


def test_knowledge_openapi_is_valid_and_documents_multipart_and_phase_boundaries():
    app = create_app(Settings(_env_file=None))
    schema = app.openapi()
    validate(schema)
    paths = schema["paths"]
    for path, model in [
        ("/api/v1/stores/{store_id}/documents", "UploadMetadata"),
        ("/api/v1/documents/{document_id}/versions", "AppendMetadata"),
    ]:
        operation = paths[path]["post"]
        assert "201" in operation["responses"] and "202" not in operation["responses"]
        assert operation["x-phase"] == "K1"
        upload = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
        assert set(upload["required"]) == {"file", "metadata"}
        assert upload["properties"]["metadata"]["contentSchema"]["title"] == model
    expected_k1 = {
        "/api/v1/stores/{store_id}/documents": {"get", "post"},
        "/api/v1/documents/{document_id}": {"get", "patch"},
        "/api/v1/documents/{document_id}/versions": {"get", "post"},
        "/api/v1/documents/{document_id}/versions/{version_id}": {"get"},
        "/api/v1/documents/{document_id}/versions/{version_id}/content": {"get"},
        "/api/v1/documents/{document_id}/control": {"post"},
    }
    expected_k2 = {
        "/api/v1/documents/{document_id}/versions/{version_id}/index-jobs": {"post"},
        "/api/v1/documents/{document_id}/index-jobs/{request_id}": {"get"},
        "/api/v1/documents/{document_id}/index-jobs/{request_id}/retry": {"post"},
        "/api/v1/documents/{document_id}/publications": {"post"},
    }
    knowledge = {path for path in paths if "/documents" in path}
    assert knowledge == expected_k1.keys() | expected_k2.keys()
    for phase, expected in (("K1", expected_k1), ("K2", expected_k2)):
        for path, methods in expected.items():
            assert set(paths[path]) == methods
            for method in methods:
                operation = paths[path][method]
                assert operation["x-phase"] == phase
                assert operation["x-implementation-status"] == "implemented"
                assert {"UserBearer": []} in operation["security"]
    assert all(
        not path.endswith(("/search", "/reindex", "/activate_index_version")) for path in knowledge
    )
    assert Settings(_env_file=None).knowledge_storage_root == "var/knowledge"
