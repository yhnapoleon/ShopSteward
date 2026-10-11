from urllib.parse import quote

from fastapi import Request, Response

from app.api.dependencies import Id, Key, User
from app.api.routing import B0Router, errors
from app.quotations import repository as repo
from app.quotations.calculator import csv_export
from app.quotations.schemas import (
    QuoteFile,
    QuoteFiles,
    QuoteProcess,
    QuoteResult,
    QuoteResults,
    QuoteRuleRemove,
    QuoteRuleState,
    QuoteUpload,
)
from app.reporting.read_router import read_transaction
from app.work_items import repository as works

router = B0Router(tags=["Quotations"], responses=errors)


@router.post(
    "/api/v1/work-items/{item_id}/quotation-files",
    response_model=QuoteFile,
    status_code=201,
    operation_id="upload_quotation_file",
)
async def upload(request: Request, principal: User, item_id: Id, body: QuoteUpload, key: Key):
    async with request.app.state.db.session() as session, session.begin():
        return await repo.upload(session, principal, item_id, body, key)


@router.get(
    "/api/v1/work-items/{item_id}/quotation-files",
    response_model=QuoteFiles,
    operation_id="list_quotation_files",
)
async def files(request: Request, principal: User, item_id: Id):
    async with read_transaction(request) as session:
        work = await works.visible(session, principal, item_id)
        return await repo.list_files(session, principal, work)


@router.get(
    "/api/v1/work-items/{item_id}/quotation-results",
    response_model=QuoteResults,
    operation_id="list_quotation_results",
)
async def results(request: Request, principal: User, item_id: Id):
    async with read_transaction(request) as session:
        work = await works.visible(session, principal, item_id)
        return await repo.list_results(session, principal, work)


@router.post(
    "/api/v1/work-items/{item_id}/quotation-results",
    response_model=QuoteResult,
    status_code=201,
    operation_id="process_quotation",
)
async def process(request: Request, principal: User, item_id: Id, body: QuoteProcess, key: Key):
    async with request.app.state.db.session() as session, session.begin():
        return await repo.direct_process(session, principal, item_id, body, key)


@router.get(
    "/api/v1/work-items/{item_id}/quotation-rule",
    response_model=QuoteRuleState,
    operation_id="get_quotation_rule",
)
async def rule(request: Request, principal: User, item_id: Id):
    async with read_transaction(request) as session:
        work = await works.visible(session, principal, item_id)
        return await repo.rule_state(session, principal, work)


@router.post(
    "/api/v1/work-items/{item_id}/quotation-rule",
    response_model=QuoteRuleState,
    operation_id="remove_quotation_rule",
)
async def remove_rule(
    request: Request, principal: User, item_id: Id, body: QuoteRuleRemove, key: Key
):
    async with request.app.state.db.session() as session, session.begin():
        return await repo.direct_remove_rule(session, principal, item_id, body, key)


def download(filename, content):
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename, safe=""),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.get(
    "/api/v1/work-items/{item_id}/quotation-files/{file_id}/download",
    response_class=Response,
    operation_id="download_quotation_file",
)
async def file_download(request: Request, principal: User, item_id: Id, file_id: Id):
    async with read_transaction(request) as session:
        work = await works.visible(session, principal, item_id)
        file = await repo.file_for_work(session, principal, work, file_id)
        return download(file.filename, file.content)


@router.get(
    "/api/v1/work-items/{item_id}/quotation-results/{result_id}/download",
    response_class=Response,
    operation_id="download_quotation_result",
)
async def result_download(request: Request, principal: User, item_id: Id, result_id: Id):
    async with read_transaction(request) as session:
        work = await works.visible(session, principal, item_id)
        result = QuoteResult.model_validate(
            (await repo.result_for_work(session, principal, work, result_id)).payload
        )
        return download(f"{result.filename[:-4]}-v{result.version}.csv", csv_export(result))
