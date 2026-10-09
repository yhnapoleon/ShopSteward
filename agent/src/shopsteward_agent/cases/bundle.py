"""Versioned text artifacts for Case strategies.

Only the components listed here can be changed by offline optimization. Safety
instructions, the output format, tools and role whitelists live in code.
"""

import json
import re
from pathlib import Path

from pydantic import Field, model_validator

from ..context.contracts import Contract, digest
from .runner import EXPERTS

EVOLVABLE = tuple(f"{kind}.{role}" for kind in ("question", "guidance") for role in EXPERTS)
# bundle id -> its evolvable components; each bundle is versioned on its own
COMPONENTS = {
    "case-experts": EVOLVABLE,
    "supplier-review": ("question.supplier", "guidance.supplier"),
}
REVISION = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"
BUNDLES = Path(__file__).parent / "bundles"


class TextBundle(Contract):
    schema_version: str = "text-bundle-v1"
    bundle_id: str = "case-experts"
    revision: str = Field(pattern=REVISION)
    parent_revision: str | None = None
    components: dict[str, str]
    content_hash: str
    provenance: dict = Field(default_factory=dict)
    gate: dict | None = None

    @model_validator(mode="after")
    def bound(self):
        allowed = COMPONENTS.get(self.bundle_id, ())
        if set(self.components) != set(allowed) or self.content_hash != digest(self.components):
            raise ValueError("bundle components or hash do not match")
        return self

    def question(self, role):
        parts = (self.components[f"question.{role}"], self.components[f"guidance.{role}"])
        return " ".join(filter(None, parts))

    def questions(self):
        """Every strategy is asked the same text, so strategies stay comparable."""
        expert = {role: self.question(role) for role in EXPERTS}
        single = " ".join(expert.values())
        return {
            **expert,
            "single": single,
            "fixed": single + " Everything needed is already in the supplied application data.",
        }


def make_bundle(
    revision, components, *, parent_revision=None, provenance=None, bundle_id="case-experts"
):
    return TextBundle(
        bundle_id=bundle_id,
        revision=revision,
        parent_revision=parent_revision,
        components=components,
        content_hash=digest(components),
        provenance=provenance or {},
    )


def load_bundle(revision="seed", *, directory=None, bundle_id="case-experts"):
    if not re.fullmatch(REVISION, revision):
        raise ValueError("invalid bundle revision")
    path = Path(directory or BUNDLES / bundle_id) / f"{revision}.json"
    bundle = TextBundle.model_validate(json.loads(path.read_text(encoding="utf-8")))
    if bundle.bundle_id != bundle_id:
        raise ValueError("bundle belongs to another artifact")
    return bundle


def save_bundle(bundle, *, directory=None):
    path = Path(directory or BUNDLES / bundle.bundle_id) / f"{bundle.revision}.json"
    if path.exists():
        raise ValueError("bundle revisions are immutable")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path
