def test_document_reference_has_compatible_scheduler_pointer_and_full_agent_reference():
    from app.agent_bridge.jobs import scheduler_references
    from app.api.schemas import JobResult

    full = dict(
        type="document",
        id="doc1",
        version_id="v1",
        generation_id="g1",
        chunk_id="c1",
        metadata_revision=1,
        locator={"kind": "paragraph", "paragraph_range": [1, 2]},
        content_sha256="a" * 64,
        original_sha256="b" * 64,
    )
    business = dict(type="store", id="store1", version="3")
    original = [full.copy(), business.copy()]
    summary = JobResult.model_validate(
        dict(summary="Agent response saved", references=scheduler_references(original))
    )
    assert summary.references[0].model_dump() == dict(type="artifact", id="doc1", version="v1")
    assert summary.references[1].model_dump() == business
    assert original == [full, business]
