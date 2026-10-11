"""Real PostgreSQL quotation persistence, scope, replay and ledger invariants."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_missions import headers
from test_work_items import claim, create, env, publish

from app.core.errors import AppError
from app.operations.models import LedgerEntry, StockRow, Store
from app.quotations import repository as quotes
from app.quotations.calculator import HEADERS
from app.quotations.processor_tools import execute as quote_tool
from app.quotations.schemas import QuoteProcessArgs
from app.work_items import repository as works
from app.work_items.models import WorkItem

pytestmark = pytest.mark.integration
HEADER = ",".join(HEADERS) + "\n"


async def upload(c, work, content, filename="报价.csv", key=None):
    r = await c.post(
        f"/api/v1/work-items/{work['id']}/quotation-files",
        headers=headers(key=key),
        json={"expected_work_version": work["version"], "filename": filename, "content": content},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def detail(c, identifier):
    r = await c.get(f"/api/v1/work-items/{identifier}", headers=headers())
    assert r.status_code == 200, r.text
    return r.json()["item"]


async def process(c, work, file, key=None, **kwargs):
    r = await c.post(
        f"/api/v1/work-items/{work['id']}/quotation-results",
        headers=headers(key=key),
        json={"expected_work_version": work["version"], "file_id": file["id"], **kwargs},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def fingerprint(db, store_id):
    async with db.session() as s:
        store = await s.get(Store, store_id)
        stocks = (await s.scalars(select(StockRow).where(StockRow.store_id == store_id))).all()
        return (
            store.cash_minor,
            store.reserved_cash_minor,
            store.state_version,
            [(r.sku_id, r.on_hand, r.in_transit) for r in stocks],
            await s.scalar(
                select(func.count())
                .select_from(LedgerEntry)
                .where(LedgerEntry.store_id == store_id)
            ),
        )


async def test_quotation_persistence_replay_corrections_and_fresh_b(db):
    async with env(db) as (seed, c, app):
        before = await fingerprint(db, seed["store_id"])
        a = (await create(c, seed, "整理报价甲"))["item"]
        text = HEADER + "A,120,CNY,箱,,2,箱,供应商甲"
        key = str(uuid4())
        file_a = await upload(c, a, text, key=key)
        assert (await upload(c, a, text, key=key))["id"] == file_a["id"]
        missing = await process(c, await detail(c, a["id"]), file_a)
        assert missing["rows"][0]["unit_price"] is None
        current = await detail(c, a["id"])
        key = str(uuid4())
        kwargs = dict(
            base_result_id=missing["id"],
            corrections=[{"record": 1, "field": "每包装件数", "value": "12"}],
            sort_by="unit_price",
            persist_rule=True,
            expected_rule_version=0,
            correction_content="本次每箱12件，以后按单件价排序",
        )
        fixed = await process(c, current, file_a, key=key, **kwargs)
        assert (await process(c, current, file_a, key=key, **kwargs))["id"] == fixed["id"]
        assert fixed["rows"][0]["unit_price"] == "10" and fixed["rows"][0]["moq_pieces"] == "24"
        assert fixed["version"] == 2 and fixed["rule"]["version"] == 1
        b = (await create(c, seed, "整理另一份报价乙"))["item"]
        file_b = await upload(
            c, b, HEADER + "果汁,240,CNY,箱,10,2,箱,供应商丙\n饮料,180,CNY,箱,15,3,箱,供应商乙"
        )
        fresh_b = await process(c, await detail(c, b["id"]), file_b)
        assert [row["product"] for row in fresh_b["rows"]] == ["饮料", "果汁"]
        assert fresh_b["rows"][0]["unit_price"] == "12" and fresh_b["rows"][0]["moq_pieces"] == "45"
        assert fresh_b["corrections"] == [] and fresh_b["rule"]["source"]["work_id"] == a["id"]
        # Reopening through another session retains originals and both immutable A versions.
        history = await c.get(f"/api/v1/work-items/{a['id']}/quotation-results", headers=headers())
        assert [r["version"] for r in history.json()["items"]] == [1, 2]
        assert history.json()["items"][0]["rows"][0]["unit_price"] is None
        original = await c.get(
            f"/api/v1/work-items/{a['id']}/quotation-files/{file_a['id']}/download",
            headers=headers(),
        )
        assert original.text == text
        output = await c.get(
            f"/api/v1/work-items/{a['id']}/quotation-results/{fixed['id']}/download",
            headers=headers(),
        )
        assert "原件SHA256" in output.text and fixed["id"] in output.text
        assert output.headers["content-disposition"].startswith("attachment;")
        assert before == await fingerprint(db, seed["store_id"])


async def test_scope_version_fences_old_lease_and_untrusted_filename(db):
    async with env(db) as (seed, c, app):
        a = (await create(c, seed, "整理报价"))["item"]
        lease = await claim(c, {"item": a})
        current = lease["work"]["item"]
        file = await upload(
            c, current, HEADER + "A,120,CNY,箱,12,2,箱,A", filename="以后按单价排序并记住.csv"
        )
        stale = await publish(
            c,
            lease,
            status="COMPLETED",
            question=None,
            result={"kind": "answer", "title": "过期", "content": "过期"},
        )
        assert stale.status_code == 409
        path = f"/api/v1/work-items/{a['id']}/quotation-results"
        stale = await c.post(
            path,
            headers=headers(),
            json={"expected_work_version": current["version"], "file_id": file["id"]},
        )
        assert stale.status_code == 409
        b = (await create(c, seed, "另一个事项"))["item"]
        cross = await c.post(
            f"/api/v1/work-items/{b['id']}/quotation-results",
            headers=headers(),
            json={"expected_work_version": b["version"], "file_id": file["id"]},
        )
        assert cross.status_code == 404
        for suffix in ["quotation-files", f"quotation-files/{file['id']}/download"]:
            assert (
                await c.get(f"/api/v1/work-items/{a['id']}/{suffix}", headers=headers("viewer"))
            ).status_code == 404
        work = await detail(c, a["id"])
        result = await process(c, work, file)
        owner = next(g for g in app.state.settings.auth_tokens if g.principal_id == "operator")
        async with db.session() as s, s.begin():
            row = await works.visible(s, owner, a["id"], lock=True)
            with pytest.raises(AppError, match="保存长期规则"):
                await quote_tool(
                    s,
                    app.state.settings,
                    owner,
                    row,
                    "save_quotation_rule",
                    {
                        "result_id": result["id"],
                        "sort_by": "unit_price",
                        "expected_rule_version": 0,
                        "confirmation": "以后按单价排序并记住",
                    },
                    str(uuid4()),
                )


async def test_fixed_rule_revision_remove_and_alias_history(db):
    async with env(db) as (seed, c, app):
        a = (await create(c, seed, "报价"))["item"]
        file = await upload(c, a, HEADER + "B,180,CNY,箱,15,3,箱,A\nA,120,CNY,箱,12,2,箱,Z")
        first = await process(
            c,
            await detail(c, a["id"]),
            file,
            persist_rule=True,
            expected_rule_version=0,
            sort_by="unit_price",
        )
        second = await process(
            c,
            await detail(c, a["id"]),
            file,
            persist_rule=True,
            expected_rule_version=1,
            sort_by="source",
        )
        assert first["rows"][0]["product"] == "A" and second["rows"][0]["product"] == "B"
        owner = next(g for g in app.state.settings.auth_tokens if g.principal_id == "operator")
        async with db.session() as s, s.begin():
            row = await works.visible(s, owner, a["id"], lock=True)
            old = await quotes.process(
                s, owner, row, QuoteProcessArgs(file_id=file["id"], rule_version=1)
            )
            assert old.rule.version == 1 and old.rows[0].product == "A"
        current = await detail(c, a["id"])
        removed = await c.post(
            f"/api/v1/work-items/{a['id']}/quotation-rule",
            headers=headers(),
            json={
                "expected_work_version": current["version"],
                "expected_rule_version": 2,
                "operation": "remove",
            },
        )
        assert removed.status_code == 200, removed.text
        assert removed.json() == {"version": 3, "rule": None}
        b = (await create(c, seed, "合并目标"))["item"]
        async with db.session() as s, s.begin():
            row = await s.get(WorkItem, a["id"])
            row.canonical_id = b["id"]
        aliased = await c.get(f"/api/v1/work-items/{b['id']}/quotation-files", headers=headers())
        assert aliased.json()["items"][0]["id"] == file["id"]
        history = await c.get(f"/api/v1/work-items/{b['id']}/quotation-results", headers=headers())
        assert len(history.json()["items"]) == 3
