import asyncio

from fastapi import Request

from app.api.dependencies import Id, Key, User, authorize_store, require_role
from app.api.routing import B0Router, errors
from app.operations_cases import repository as cases
from app.operations_cases.schemas import CaseDetail, CaseSource
from app.sourcing import repository as repo
from app.sourcing import run
from app.sourcing.schemas import (
    SampleDocuments,
    SupplierDocumentSet,
    SupplierDocumentsUpdate,
    TextBundleList,
)

router = B0Router(tags=["Sourcing"], responses=errors)


@router.get(
    "/api/v1/stores/{store_id}/supplier-documents",
    response_model=SupplierDocumentSet,
    operation_id="list_supplier_documents",
)
async def documents(request: Request, principal: User, store_id: Id):
    authorize_store(principal, store_id)
    async with request.app.state.db.session() as session:
        return await repo.listing(session, store_id)


@router.post(
    "/api/v1/stores/{store_id}/supplier-documents",
    response_model=SupplierDocumentSet,
    operation_id="replace_supplier_documents",
)
async def replace(request: Request, principal: User, store_id: Id, body: SupplierDocumentsUpdate):
    require_role(principal, "operator")
    authorize_store(principal, store_id)
    async with request.app.state.db.session() as session, session.begin():
        await repo.replace(
            session,
            store_id,
            body.supplier_id,
            body.name,
            [doc.model_dump() for doc in body.documents],
        )
        return await repo.listing(session, store_id)


@router.post(
    "/api/v1/stores/{store_id}/supplier-documents/sample",
    response_model=SupplierDocumentSet,
    operation_id="load_sample_supplier_documents",
)
async def sample(request: Request, principal: User, store_id: Id, body: SampleDocuments):
    """Three invented suppliers' documents about one item, for trying the sourcing loop."""
    require_role(principal, "operator")
    authorize_store(principal, store_id)
    async with request.app.state.db.session() as session, session.begin():
        await repo.load_sample(session, store_id, body.sku_id, body.district)
        return await repo.listing(session, store_id)


@router.post(
    "/api/v1/operations-cases/{case_id}/source",
    response_model=CaseDetail,
    operation_id="source_operations_case",
)
async def source(request: Request, principal: User, case_id: Id, body: CaseSource, key: Key):
    """Start the reviewers; the Case shows their cards as they finish."""
    require_role(principal, "operator")
    state = request.app.state
    async with state.db.session() as session, session.begin():
        row = await cases.visible(session, principal, case_id, lock=True)
        result, work = await run.start(session, row, body, principal, key, state.settings)
    if work:
        task = asyncio.create_task(run.execute(state.db, state.settings, principal, case_id, work))
        # The loop keeps only weak references to tasks; hold this one until it is done.
        state.sourcing_tasks.add(task)
        task.add_done_callback(state.sourcing_tasks.discard)
    return result


@router.get("/api/v1/text-bundles", response_model=TextBundleList, operation_id="list_text_bundles")
async def bundles(request: Request, principal: User):
    return TextBundleList(items=repo.text_bundles(request.app.state.settings))
