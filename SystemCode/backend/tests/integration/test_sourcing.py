"""Sourcing on a recovery Case: documents in, gated cards, offers, then the usual path."""

import asyncio
import json
import re
from datetime import datetime, timedelta

import pytest
from test_execution import Supplier, approve, execute, isolated_actions  # noqa: F401
from test_missions import clean_queue, environment, headers  # noqa: F401
from test_operations_cases import adopt_body
from test_planning_jobs import start

pytestmark = pytest.mark.integration
USAGE = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}


async def short_case(db, seed, client):
    """A store that runs out on day three, with only its own connected supplier on file."""
    from app.missions.models import InboundRow, MissionRow
    from app.operations.models import OfferRow, StockRow, Store

    mission = await start(client, seed)
    clock = datetime.fromisoformat(seed["simulation_time"])
    async with db.session() as session, session.begin():
        store = await session.get(Store, seed["store_id"])
        store.cash_minor = 80000
        row = await session.get(MissionRow, mission["id"])
        row.policy = row.policy | {"cash_floor_minor": 50000}
        stock = await session.get(StockRow, (store.id, "sku_001"))
        stock.on_hand, stock.in_transit = 20, 50
        original = await session.get(OfferRow, (store.id, "sku_001", "supplier_001"))
        original.document = original.document | {"unit_price_minor": 900, "pack_size": 10}
        session.add(
            InboundRow(
                action_id="original-" + store.id,
                store_id=store.id,
                sku_id="sku_001",
                ordered_qty=50,
                received_qty=0,
                expected_arrival_at=clock + timedelta(days=4),
            )
        )
    body = {
        "mission_id": mission["id"],
        "objective": "原订单晚到，找其他供应商补上缺口",
        "budget_minor": 30000,
        "daily_demand": [
            {"settlement_at": (clock + timedelta(days=i, hours=23)).isoformat(), "demand_qty": 10}
            for i in range(7)
        ],
    }
    response = await client.post("/api/v1/operations-cases", json=body, headers=headers())
    assert response.status_code == 201, response.text
    return response.json()


def line(document, needle):
    return next(row for row in document["text"].splitlines() if needle in row)


def cards(suppliers):
    """What a careful reader returns for the three sample suppliers, each field with its line."""
    docs = {doc["doc_id"]: doc for supplier in suppliers for doc in supplier["documents"]}

    def offer(sid, price, lead, priced_in):
        quote = docs[f"{sid}-quote"]
        row, valid = line(quote, "sku_001"), line(quote, "有效期")
        start_day, end_day = re.findall(r"\d{4}-\d{2}-\d{2}", valid)
        return {
            "supplier_id": sid,
            "status": "offer",
            "reason": None,
            "offer": {
                "unit_price_minor": price,
                "minimum_order_quantity": 20,
                "pack_size": 10,
                "lead_time_days": lead,
                "valid_from": start_day,
                "valid_until": end_day,
                "offer_version": f"BJ-{sid}-01",
            },
            "history": {"deliveries": 5, "late": 1 if sid == "A" else 0},
            "citations": [
                {
                    "field": "unit_price_minor",
                    "doc_id": priced_in,
                    "quote": line(docs[priced_in], "sku_001"),
                },
                {"field": "minimum_order_quantity", "doc_id": f"{sid}-quote", "quote": row},
                {"field": "lead_time_days", "doc_id": f"{sid}-quote", "quote": row},
                {"field": "valid_until", "doc_id": f"{sid}-quote", "quote": valid},
            ],
        }

    return {
        # A's price is the one its notice in force gives, not the one on the quote.
        "A": offer("A", 920, 2, "A-notice-1"),
        # B prices by the case of ten: 86.00 a case is 8.60 a unit.
        "B": offer("B", 860, 1, "B-quote"),
        "C": {
            "supplier_id": "C",
            "status": "no_offer",
            "reason": "STORE_NOT_SERVED",
            "offer": None,
            "history": {"deliveries": 0, "late": 0},
            "citations": [
                {
                    "field": "status",
                    "doc_id": "C-terms",
                    "quote": line(docs["C-terms"], "配送范围为"),
                }
            ],
        },
    }


class Desk:
    """Plays every reviewer and the explainer."""

    def __init__(self, answers, *, held=False):
        self.answers, self.explained = answers, []
        # Held: nobody answers until released, so a test can look at a run in progress.
        self.released = asyncio.Event()
        if not held:
            self.released.set()

    async def complete(self, messages, tools, **kwargs):
        await self.released.wait()
        text = "\n".join(str(message.get("content")) for message in messages)
        if not any(tool["function"]["name"] == "read_supplier_document" for tool in tools):
            self.explained.append(text)
            evidence = json.loads(
                "[" + re.search(r'"evidence_ids": \[([^\]]*)\]', text).group(1) + "]"
            )
            chosen = re.search(r'"recommended_candidate_id": "(\w+)"', text).group(1)
            claim = {
                "statement": f"{chosen} is recommended",
                "support": [evidence[-1]],
                "kind": "calculation",
                "subject": {"type": "candidate", "id": chosen},
                "applicability": {"result": "recommended"},
            }
            answer = {"claims": [claim], "missing": [], "followup_requests": []}
            return {"content": json.dumps(answer), "usage": USAGE}
        sid = re.search(r'"supplier": \{"supplier_id": "(\w+)"', text).group(1)
        if not any(message["role"] == "tool" for message in messages):
            listed = json.loads(text[text.index('{"role": "supplier"') :].split("\n")[0])
            calls = [
                {
                    "id": f"{sid}-{index}",
                    "function": {
                        "name": "read_supplier_document",
                        "arguments": json.dumps({"doc_id": doc["doc_id"]}),
                    },
                }
                for index, doc in enumerate(listed["documents"])
            ]
            return {"content": "", "usage": USAGE, "tool_calls": calls}
        return {"content": json.dumps(self.answers[sid], ensure_ascii=False), "usage": USAGE}


async def test_documents_become_gated_offers_and_the_purchase_is_sent_by_the_owner(db, monkeypatch):
    import shopsteward_agent

    async with environment(db) as (seed, client):
        app = client._transport.app
        settings = app.state.settings
        # No experts flag: a sourced proposal is explained whenever a Case model exists.
        settings.agent_case_model = "test-model"
        settings.agent_api_key_file = "test-provider-does-not-read-this"
        settings.agent_max_input_tokens = 64000
        case = await short_case(db, seed, client)
        store = seed["store_id"]
        source = f"/api/v1/operations-cases/{case['id']}/source"
        nothing = await client.post(source, json={"expected_revision": 1}, headers=headers())
        assert nothing.json()["error"]["code"] == "SUPPLIER_DOCUMENTS_REQUIRED"

        documents = f"/api/v1/stores/{store}/supplier-documents"
        sample = {"sku_id": "sku_001"}
        assert (
            await client.post(documents + "/sample", json=sample, headers=headers("viewer"))
        ).status_code == 403
        loaded = await client.post(documents + "/sample", json=sample, headers=headers())
        assert loaded.status_code == 200, loaded.text
        suppliers = (await client.get(documents, headers=headers("viewer"))).json()["suppliers"]
        assert [(s["supplier_id"], len(s["documents"])) for s in suppliers] == [
            ("A", 4),
            ("B", 3),
            ("C", 3),
        ]
        # The store's own connected supplier cannot be given a second, document-based offer.
        own = {"supplier_id": "supplier_001", "name": "x", "documents": []}
        assert (await client.post(documents, json=own, headers=headers())).status_code == 409

        desk = Desk(cards(suppliers), held=True)
        monkeypatch.setattr(shopsteward_agent, "OpenAIModel", lambda **kwargs: desk)
        started = await client.post(source, json={"expected_revision": 1}, headers=headers())
        assert started.status_code == 200, started.text
        running = started.json()["sourcing"]
        assert running["status"] == "running"
        assert (running["request"]["shortfall_qty"], running["request"]["district"]) == (
            20,
            "滨江区",
        )
        again = await client.post(source, json={"expected_revision": 1}, headers=headers())
        assert again.json()["error"]["code"] == "SOURCING_IN_PROGRESS"
        desk.released.set()
        await asyncio.gather(*list(app.state.sourcing_tasks))

        done = (
            await client.get(f"/api/v1/operations-cases/{case['id']}", headers=headers())
        ).json()
        sourcing = done["sourcing"]
        assert (sourcing["status"], sourcing["unreviewed"]) == ("complete", [])
        # Cheapest first; C is read, found not to deliver here, and offers nothing.
        assert sourcing["registered"] == ["B", "A"]
        reviewed = {review["supplier_id"]: review for review in sourcing["reviews"]}
        assert reviewed["C"]["card"]["reason"] == "STORE_NOT_SERVED"
        assert reviewed["A"]["card"]["offer"]["unit_price_minor"] == 920
        assert reviewed["A"]["attempts"][0]["opened"] == [
            "A-history",
            "A-notice-1",
            "A-quote",
            "A-terms",
        ]
        assert sourcing["review_bundle"]["revision"] == "seed"

        # The Case moved to a new revision that compares exactly what was read, and solved it.
        assert (done["current_revision"], done["supplier_ids"]) == (2, ["B", "A"])
        assert done["status"] == "OPTIONS_READY"
        assert done["proposal"]["recommended_candidate_id"] == "B_20"
        read = [item for item in done["evidence"] if item["kind"] == "supplier_offer"]
        assert all("寻源" in item["summary"] for item in read) and len(read) == 2
        # The explanation ran on the evolved text and was shown the cards.
        analysis = done["expert_analysis"]
        assert analysis["status"] == "complete"
        assert analysis["routing"]["bundle_revision"] == "sourcing-r1-s1"
        assert len(desk.explained) == 1 and "STORE_NOT_SERVED" in desk.explained[0]
        catalog = (await client.get(f"/api/v1/catalog?store_id={store}", headers=headers())).json()
        assert sorted(offer["supplier_id"] for offer in catalog["offers"]) == [
            "A",
            "B",
            "supplier_001",
        ]

        # Adopt and approve as usual; a supplier known only from documents is ordered by hand.
        adopted = await client.post(
            f"/api/v1/operations-cases/{case['id']}/materialize",
            json=adopt_body(done),
            headers=headers(),
        )
        assert adopted.status_code == 200, adopted.text
        plan = (
            await client.get(f"/api/v1/plans/{adopted.json()['plan_id']}", headers=headers())
        ).json()
        accepted = await approve(client, plan)
        supplier = Supplier()
        await execute(db, seed, supplier)
        assert supplier.calls == []
        action = (
            await client.get(f"/api/v1/actions/{accepted['action_id']}", headers=headers())
        ).json()
        assert (action["channel"], action["status"]) == ("assisted", "EXECUTING")
        order = action["order_message"]
        assert (order["supplier_id"], order["quantity"], order["total_minor"]) == ("B", 20, 17200)
        replied = await client.post(
            f"/api/v1/actions/{action['id']}/supplier-reply",
            json={"text": "收到，确认20件，单价8.60元/件"},
            headers=headers("approver"),
        )
        assert replied.status_code == 200, replied.text
        assert replied.json()["status"] == "SUCCEEDED"


async def test_a_card_the_gate_rejects_twice_leaves_that_supplier_out_and_says_why(db, monkeypatch):
    import shopsteward_agent

    async with environment(db) as (seed, client):
        app = client._transport.app
        settings = app.state.settings
        # Only the readers have a model here; nothing is configured for the explanation.
        settings.agent_sourcing_model = "test-reader"
        settings.agent_sourcing_api_key_file = "test-provider-does-not-read-this"
        settings.agent_max_input_tokens = 64000
        case = await short_case(db, seed, client)
        documents = f"/api/v1/stores/{seed['store_id']}/supplier-documents"
        loaded = await client.post(
            documents + "/sample", json={"sku_id": "sku_001"}, headers=headers()
        )
        answers = cards(loaded.json()["suppliers"])
        # B's reviewer reports the price of a case as the price of a unit and quotes nothing real.
        answers["B"] = json.loads(json.dumps(answers["B"]))
        answers["B"]["citations"][0]["quote"] = "单价 8.60 元/件"
        monkeypatch.setattr(shopsteward_agent, "OpenAIModel", lambda **kwargs: Desk(answers))
        started = await client.post(
            f"/api/v1/operations-cases/{case['id']}/source",
            json={"expected_revision": 1},
            headers=headers(),
        )
        assert started.status_code == 200, started.text
        await asyncio.gather(*list(app.state.sourcing_tasks))
        done = (
            await client.get(f"/api/v1/operations-cases/{case['id']}", headers=headers())
        ).json()
        sourcing = done["sourcing"]
        assert (sourcing["status"], sourcing["unreviewed"], sourcing["registered"]) == (
            "partial",
            ["B"],
            ["A"],
        )
        attempts = next(r for r in sourcing["reviews"] if r["supplier_id"] == "B")["attempts"]
        assert [attempt["problems"] for attempt in attempts] == [["uncited:unit_price_minor"]] * 2
        assert {attempt["model"] for attempt in attempts} == {"test-reader"}
        assert "is not found word for word in B-quote" in attempts[0]["reasons"][0]
        assert done["proposal"]["recommended_candidate_id"] == "A_20"
        # Without a Case model sourcing still ends with a solved Case, just unexplained.
        assert done["expert_analysis"] is None


async def test_a_supplier_the_case_left_out_is_not_read_again(db, monkeypatch):
    import shopsteward_agent

    async with environment(db) as (seed, client):
        app = client._transport.app
        settings = app.state.settings
        settings.agent_sourcing_model = "test-reader"
        settings.agent_sourcing_api_key_file = "test-provider-does-not-read-this"
        settings.agent_max_input_tokens = 64000
        case = await short_case(db, seed, client)
        documents = f"/api/v1/stores/{seed['store_id']}/supplier-documents"
        loaded = await client.post(
            documents + "/sample", json={"sku_id": "sku_001"}, headers=headers()
        )
        answers = cards(loaded.json()["suppliers"])
        monkeypatch.setattr(shopsteward_agent, "OpenAIModel", lambda **kwargs: Desk(answers))
        path = f"/api/v1/operations-cases/{case['id']}"

        async def leave_out(revision, suppliers):
            response = await client.post(
                path + "/revise",
                json={"expected_revision": revision, "excluded_supplier_ids": suppliers},
                headers=headers(),
            )
            assert response.status_code == 200, response.text
            return response.json()

        assert (await leave_out(1, ["A", "B", "C"]))["excluded_supplier_ids"] == ["A", "B", "C"]
        nobody = await client.post(
            path + "/source", json={"expected_revision": 2}, headers=headers()
        )
        assert nobody.json()["error"]["code"] == "NO_OTHER_SUPPLIERS"
        await leave_out(2, ["B"])
        started = await client.post(
            path + "/source", json={"expected_revision": 3}, headers=headers()
        )
        assert started.status_code == 200, started.text
        running = started.json()["sourcing"]
        assert [s["supplier_id"] for s in running["suppliers"]] == ["A", "C"]
        assert running["excluded"] == ["B"]
        await asyncio.gather(*list(app.state.sourcing_tasks))
        done = (await client.get(path, headers=headers())).json()
        assert done["sourcing"]["registered"] == ["A"]
        assert done["excluded_supplier_ids"] == ["B"]
        assert {c["supplier_id"] for c in done["proposal"]["candidates"]} <= {None, "A"}


async def test_text_bundles_list_what_evolution_changed_and_where_each_runs(db):
    async with environment(db) as (seed, client):
        listed = (await client.get("/api/v1/text-bundles", headers=headers("viewer"))).json()
        by_name = {(item["bundle_id"], item["revision"]): item for item in listed["items"]}
        evolved = by_name[("case-experts", "sourcing-r1-s1")]
        assert (evolved["parent_revision"], evolved["origin"], evolved["stage"]) == (
            "seed",
            "gepa",
            "explain",
        )
        assert evolved["enabled_for"] == ["sourcing_explanation"]
        assert {change["component"] for change in evolved["changes"]} <= {
            "question.evidence",
            "question.impact",
            "guidance.evidence",
            "guidance.impact",
        } and evolved["changes"]
        assert by_name[("case-experts", "seed")]["enabled_for"] == ["case_explanation"]
        assert by_name[("supplier-review", "seed")]["enabled_for"] == ["supplier_review"]


async def test_live_model_reads_the_sample_documents(db):
    """Opt-in: one sourcing run and one reply reading on real models, printed for inspection.

    SOURCING_LIVE_KEY_FILE names the readers' key file; _MODEL, _BASE_URL and _API_MODE
    default to deepseek-flash at DeepSeek. SOURCING_LIVE_CASE_KEY_FILE, _CASE_MODEL,
    _CASE_BASE_URL and _CASE_API_MODE put the explanation at another provider; unset, it
    runs where the readers do. Run with -s.
    """
    import os

    env = os.environ.get
    if not env("SOURCING_LIVE_KEY_FILE"):
        pytest.skip("Set SOURCING_LIVE_KEY_FILE to read the sample documents with a real model")
    from app.execution import assisted

    async with environment(db) as (seed, client):
        app = client._transport.app
        settings = app.state.settings
        settings.agent_sourcing_api_key_file = env("SOURCING_LIVE_KEY_FILE")
        settings.agent_sourcing_base_url = env("SOURCING_LIVE_BASE_URL", "https://api.deepseek.com")
        settings.agent_sourcing_model = env("SOURCING_LIVE_MODEL", "deepseek-flash")
        settings.agent_sourcing_api_mode = env("SOURCING_LIVE_API_MODE", "chat_completions")
        settings.agent_api_key_file = env(
            "SOURCING_LIVE_CASE_KEY_FILE", settings.agent_sourcing_api_key_file
        )
        settings.agent_base_url = env(
            "SOURCING_LIVE_CASE_BASE_URL", settings.agent_sourcing_base_url
        )
        settings.agent_case_model = env("SOURCING_LIVE_CASE_MODEL", settings.agent_sourcing_model)
        settings.agent_case_api_mode = env(
            "SOURCING_LIVE_CASE_API_MODE", settings.agent_sourcing_api_mode
        )
        settings.agent_case_experts_enabled = True
        settings.agent_max_input_tokens = 64000
        settings.agent_max_output_tokens = 16000
        settings.agent_model_timeout_seconds = 120
        case = await short_case(db, seed, client)
        documents = f"/api/v1/stores/{seed['store_id']}/supplier-documents"
        await client.post(documents + "/sample", json={"sku_id": "sku_001"}, headers=headers())
        started = await client.post(
            f"/api/v1/operations-cases/{case['id']}/source",
            json={"expected_revision": 1},
            headers=headers(),
        )
        assert started.status_code == 200, started.text
        await asyncio.gather(*list(app.state.sourcing_tasks))
        done = (
            await client.get(f"/api/v1/operations-cases/{case['id']}", headers=headers())
        ).json()
        sourcing = done["sourcing"]
        print("\nsourcing:", sourcing["status"], "registered:", sourcing.get("registered"))
        for review in sourcing["reviews"]:
            card = review["card"]
            print(
                " ",
                review["supplier_id"],
                [(attempt["model"], attempt["problems"]) for attempt in review["attempts"]],
                card and (card["offer"] or card["reason"]),
            )
        print("  readers:", sourcing.get("budget", {}).get("usage"))
        print("recommended:", done["proposal"] and done["proposal"]["recommended_candidate_id"])
        analysis = done["expert_analysis"] or {}
        print(
            "explanation:",
            analysis.get("status"),
            analysis.get("routing", {}).get("bundle_revision"),
            (analysis.get("profile") or {}).get("model_id"),
            analysis.get("usage"),
        )
        for task in analysis.get("subtasks", []):
            claims = task.get("claims", [])
            print("  claims:", len(claims), "missing:", task.get("missing"))
            for claim in claims[:6]:
                print("  -", claim["statement"][:200])
        assert sourcing["status"] in {"complete", "partial"} and sourcing["registered"]
        assert done["status"] == "OPTIONS_READY"

        order = {"quantity": 20, "unit_price_minor": 860, "total_minor": 17200, "currency": "CNY"}
        words = "好嘞老板，20件没问题，还是八块六一件，周四给你送过去"
        today = datetime.fromisoformat(seed["simulation_time"]).date()
        reading, read_by = await assisted.read_reply(
            words, order, today, model=assisted.reader(settings)
        )
        print("reply read by", read_by, "on", today.isoformat(), ":", reading)
        assert reading["decision"] in {"accepted", "rejected", "unclear"}
