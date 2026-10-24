"""One task ledger shared by root, experts, retries and repair calls."""

import asyncio
import time

from ..runtime import Runtime, RuntimeFailure


class CallBudget:
    def __init__(self, *, max_model_calls=14, max_tool_calls=28, timeout_s=150, persist=None):
        self.max_model_calls = max_model_calls
        self.max_tool_calls = max_tool_calls
        self.deadline = time.time() + timeout_s
        self.entries = {}
        self.persist = persist
        self.lock = asyncio.Lock()

    async def reserve(self, call_id, kind):
        if kind not in {"model", "tool"}:
            raise ValueError("unsupported reservation kind")
        async with self.lock:
            if time.time() >= self.deadline:
                raise RuntimeFailure("run_deadline")
            if call_id in self.entries:
                # An interrupted call may have reached the provider. Never turn
                # replay of the same reservation into an uncounted new attempt.
                raise RuntimeFailure("reservation_already_used")
            maximum = self.max_model_calls if kind == "model" else self.max_tool_calls
            if sum(entry["kind"] == kind for entry in self.entries.values()) >= maximum:
                raise RuntimeFailure(kind + "_budget")
            self.entries[call_id] = {"kind": kind, "status": "reserved", "usage": None}
            if self.persist is not None:
                await self.persist(self.snapshot())

    async def settle(self, call_id, usage, status):
        async with self.lock:
            self.entries[call_id] = {**self.entries[call_id], "usage": usage, "status": status}
            if self.persist is not None:
                await self.persist(self.snapshot())

    def snapshot(self):
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        for entry in self.entries.values():
            if entry["kind"] == "model":
                usage = Runtime.add_usage({"usage": usage}, entry["usage"])
        return {
            "schema_version": "case-budget-v1",
            "max_model_calls": self.max_model_calls,
            "max_tool_calls": self.max_tool_calls,
            "deadline": self.deadline,
            "model_calls": sum(e["kind"] == "model" for e in self.entries.values()),
            "tool_calls": sum(e["kind"] == "tool" for e in self.entries.values()),
            "entries": {key: dict(value) for key, value in self.entries.items()},
            "usage": usage,
            "cost_status": "unknown",
        }

    @classmethod
    def from_snapshot(cls, snapshot, *, persist=None):
        budget = cls(
            max_model_calls=snapshot["max_model_calls"],
            max_tool_calls=snapshot["max_tool_calls"],
            persist=persist,
        )
        budget.deadline = snapshot["deadline"]
        budget.entries = {key: dict(value) for key, value in snapshot["entries"].items()}
        return budget
