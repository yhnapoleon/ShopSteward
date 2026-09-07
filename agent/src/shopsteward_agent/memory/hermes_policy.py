"""Pure adaptation of Hermes MemoryStore add/_edit/apply_batch and unique matching.
Upstream: NousResearch/hermes-agent 693641aa8b4359c602283bdbbc14041e03bc47bc
Source: tools/memory_tool_store.py. MIT; see THIRD_PARTY_NOTICES.md.
Changed: no filesystem, locks, globals, frozen prompts or approval integration;
returns copied entries, final batch budget; backend owns identity/revision/security.
"""

LIMITS = {"USER": 1375, "NOTES": 2200}


def apply_memory_changes(entries, changes, target):
    if target not in LIMITS:
        raise ValueError("invalid_target")
    result = list(dict.fromkeys(entries))
    for change in changes:
        action = change.get("action")
        content = change.get("content", "").strip()
        if action == "add":
            if not content:
                raise ValueError("empty_content")
            if content not in result:
                result.append(content)
        elif action in ("replace", "remove"):
            old = change.get("old_text", "").strip()
            if not old:
                raise ValueError("empty_match")
            matches = [i for i, entry in enumerate(result) if old in entry]
            if len({result[i] for i in matches}) > 1:
                raise ValueError("ambiguous_match")
            if not matches:
                raise ValueError("missing_match")
            if action == "remove":
                result.pop(matches[0])
            else:
                if not content:
                    raise ValueError("empty_content")
                result[matches[0]] = content
        else:
            raise ValueError("invalid_action")
    result = list(dict.fromkeys(result))
    if len("\n§\n".join(result)) > LIMITS[target]:
        raise ValueError("memory_budget")
    return result
