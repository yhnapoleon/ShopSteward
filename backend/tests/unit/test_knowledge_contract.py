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
    knowledge = {path for path in paths if "/documents" in path}
    assert len(knowledge) == 6
    assert all(
        not path.endswith(("/search", "/reindex", "/activate_index_version")) for path in knowledge
    )
    assert Settings(_env_file=None).knowledge_storage_root == "var/knowledge"
