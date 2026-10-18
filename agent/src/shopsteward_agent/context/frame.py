import re
from decimal import Decimal

from .contracts import Constraint, TaskFrame, digest
from .intent import classify_intent


def apply_patch(frame: TaskFrame, patches: list[dict], sources: dict[str, str]) -> TaskFrame:
    """Validate source-backed proposals. This function never changes business state."""
    constraints = {(c.key, c.scope): c for c in frame.constraints}
    seen = set()
    for raw in patches:
        patch = Constraint.model_validate(raw)
        identity = (patch.key, patch.scope)
        if identity in seen:
            raise ValueError("duplicate constraint key")
        seen.add(identity)
        text = sources.get(patch.source_message_id)
        start, end = patch.source_span
        if text is None or start < 0 or end <= start or text[start:end] != patch.exact_quote:
            raise ValueError("constraint quote does not match source")
        if any((key, patch.scope) not in constraints for key in patch.supersedes):
            raise ValueError("unknown superseded constraint")
        if patch.operator == "unset":
            constraints.pop(identity, None)
        else:
            constraints[identity] = patch
    payload = [c.model_dump(mode="json") for c in constraints.values()]
    return TaskFrame(
        run_id=frame.run_id,
        parent_frame_id=frame.frame_id,
        frame_id=digest({"parent": frame.frame_id, "patches": patches}),
        constraints=list(constraints.values()),
        validation_status="validated",
        source_message_ids=sorted({c.source_message_id for c in constraints.values()}),
        source_digest=digest(payload),
    )


def valid_dependencies(expected: dict, current: dict) -> bool:
    return all(key in current and current[key] == value for key, value in expected.items())


def extract_frame(run_id: str, messages: list[dict]) -> TaskFrame:
    """A deliberately bounded, source-checked extractor, never a business writer.

    Supports explicit Chinese budget-in-yuan/minor-unit and item count commands.
    Unmatched text remains in the model view; ambiguous recognized commands are
    surfaced. Model-generated summaries are never used as user source evidence.
    """
    frame = TaskFrame(run_id=run_id)
    patterns = {
        "budget": re.compile(
            r"预算\s*(?:最多|不超过|上限|为|是|改为|改成|调整为)?\s*(-?\d+(?:\.\d{1,2})?)\s*(元|分)"
        ),
        "quantity": re.compile(
            r"(最多|不超过|至少|恰好|正好|数量上限(?:为|改成|改为|调整为)?|上限为)\s*(-?\d+)\s*(?:件|个)"
        ),
    }
    cancellations = {
        "budget": re.compile(r"取消预算(?:上限|限制)|预算不限|不设预算上限"),
        "quantity": re.compile(r"取消(?:数量|采购数量)?上限|取消数量限制|数量不限"),
    }
    unresolved = []
    extracted = False
    effect = classify_intent(messages)
    for message in messages:
        text, source_id = message["content"], message["message_id"]
        denied = classify_intent([message])["requested_effect"] == "read_only"
        if re.search(r"记住|偏好|记忆|默认|习惯", text) and "本次" not in text:
            # Long-term preferences belong to current KnowledgeScope versions.
            # They must not be resurrected from historical message extraction.
            continue
        scenario = bool(denied or re.search(r"假如|假设|如果|试算|模拟|what if|suppose", text, re.I))
        scope = "scenario" if scenario else "one_run"
        # Hypotheticals last only for the current utterance and cannot overwrite
        # previously established actual constraints.
        frame = frame.model_copy(
            update={"constraints": [c for c in frame.constraints if c.scope != "scenario"]}
        )
        for key in ("budget", "quantity"):
            matches = list(patterns[key].finditer(text))
            cancel = cancellations[key].search(text)
            if key == "quantity" and scenario and not matches:
                matches = list(re.finditer(r"买\s*(-?\d+)\s*件", text))
            patch = None
            if cancel and not matches:
                patch = {
                    "key": key,
                    "operator": "unset",
                    "source_span": cancel.span(),
                    "exact_quote": cancel.group(),
                }
            elif len(matches) == 1 and not cancel:
                match = matches[0]
                if key == "budget":
                    value = int(Decimal(match.group(1)) * (100 if match.group(2) == "元" else 1))
                    operator, unit = "lte", "minor"
                else:
                    groups = match.groups()
                    if len(groups) == 1:
                        value, operator = int(groups[0]), "eq"
                    else:
                        value = int(groups[1])
                        operator = (
                            "eq"
                            if groups[0] in {"恰好", "正好"}
                            else "gte"
                            if groups[0] == "至少"
                            else "lte"
                        )
                    unit = "item"
                if value >= 0:
                    patch = {
                        "key": key,
                        "operator": operator,
                        "value": value,
                        "unit": unit,
                        "source_span": match.span(),
                        "exact_quote": match.group(),
                    }
            cue = r"预算" if key == "budget" else r"最多|至少|恰好|数量上限|数量限制"
            if patch:
                patch.update(source_message_id=source_id, scope=scope)
                frame = apply_patch(frame, [patch], {source_id: text})
                extracted = True
                unresolved = [item for item in unresolved if not item.startswith(key + "_")]
            elif (matches or cancel or re.search(cue, text)) and re.search(r"\d|取消|不限", text):
                unresolved.append(f"{key}_unparsed:{source_id}")
    payload = {
        "messages": messages,
        "constraints": [c.model_dump(mode="json") for c in frame.constraints],
    }
    return frame.model_copy(
        update={
            "frame_id": digest(payload),
            "source_digest": digest(messages),
            "source_message_ids": [message["message_id"] for message in messages],
            "validation_status": "validated" if extracted else "raw_fallback",
            "unresolved": unresolved,
            **effect,
        }
    )
