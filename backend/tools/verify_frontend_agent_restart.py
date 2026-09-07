"""Read-only snapshot comparison for existing frontend/Agent acceptance scenarios.

Run from backend: python tools/verify_frontend_agent_restart.py --capture
After restarting the local stack: python tools/verify_frontend_agent_restart.py
Creates no purchases or messages. Only reads local development data and writes
the acceptance report; credentials are read privately from backend/.env.
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.agent_bridge.models import Conversation  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.db.session import Database  # noqa: E402
from app.missions.models import MissionRow as Mission  # noqa: E402
from app.operations.models import Store  # noqa: E402

REPORT = ROOT / "docs/api/frontend-agent-restart-result.json"


async def select_scenarios():
    db = Database(Settings().database_url.get_secret_value())
    try:
        async with db.session() as session:
            conversations = (
                await session.scalars(
                    select(Conversation).order_by(Conversation.created_at.desc()).limit(3)
                )
            ).all()
            sc01 = await session.scalar(
                select(Mission)
                .join(Store, Store.id == Mission.store_id)
                .where(Store.cash_minor == 40000, Store.receivables_minor == 20000)
                .order_by(Mission.created_at.desc())
                .limit(1)
            )
            if not sc01 or len(conversations) != 3:
                raise RuntimeError("Run the business and real-Agent frontend acceptance first.")
            return {
                "stores": sorted({sc01.store_id, *(c.store_id for c in conversations)}),
                "conversations": [c.id for c in conversations],
                "sc01_store": sc01.store_id,
            }
    finally:
        await db.dispose()


def snapshot(selection):
    with httpx.Client(base_url="http://127.0.0.1:3000", timeout=15, trust_env=False) as client:
        session = client.get("/api/session")
        session.raise_for_status()
        assert session.json()["authenticated"] and session.json()["agentEnabled"]

        def get(path):
            response = client.get("/api/backend/api/v1/" + path)
            response.raise_for_status()
            return response.json()

        stores = {}
        for store in selection["stores"]:
            stores[store] = {"state": get(f"dashboard?store_id={store}")["state"]}
            for resource in ("actions", "inbounds", "ledger-entries"):
                data = get(f"{resource}?store_id={store}&limit=100")
                assert not data.get("next_cursor"), "Capture must include all acceptance records"
                stores[store][resource] = data["items"]
            stores[store]["knowledge"] = get(f"stores/{store}/agent-knowledge")
        conversations = {}
        for cid in selection["conversations"]:
            messages = get(f"conversations/{cid}/messages?limit=100")
            assert messages["next_after_seq"] is None
            runs = {
                m["run_id"]: get("agent-runs/" + m["run_id"])
                for m in messages["items"]
                if m["run_id"]
            }
            assert all(r["status"] in {"SUCCEEDED", "CANCELLED", "FAILED"} for r in runs.values())
            conversations[cid] = {"messages": messages, "runs": runs}
        state = stores[selection["sc01_store"]]["state"]
        assert state["cash_minor"] == 40000 and state["receivables_minor"] == 20000
        assert state["reserved_cash_minor"] == 0
        assert state["stocks"][0]["on_hand"] == 70 and state["stocks"][0]["in_transit"] == 0
        return {"stores": stores, "conversations": conversations}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true")
    args = parser.parse_args()
    if args.capture:
        selection = asyncio.run(select_scenarios())
        result = {
            "captured_at": datetime.now(UTC).isoformat(),
            "selection": selection,
            "before": snapshot(selection),
        }
    else:
        result = json.loads(REPORT.read_text(encoding="utf-8"))
        current = snapshot(result["selection"])
        result.update(
            verified_at=datetime.now(UTC).isoformat(), unchanged=current == result["before"]
        )
        if not result["unchanged"]:
            result["after"] = current
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "report": str(REPORT),
                "stores": len(result["selection"]["stores"]),
                "conversations": len(result["selection"]["conversations"]),
                "unchanged": result.get("unchanged"),
            },
            indent=2,
        )
    )
    if not args.capture and not result["unchanged"]:
        raise SystemExit("Restart changed captured business or Agent data; inspect report.")


if __name__ == "__main__":
    main()
