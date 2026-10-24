"""Field allowlists: arbitrary model/user text is not an execution trace."""

ARGUMENTS = {
    "budget_minor",
    "quantity",
    "max_purchase_qty",
    "plan_id",
    "case_id",
    "expected_revision",
    "expected_version",
    "supplier_ids",
}
RESULTS = {"ok", "status", "error_code", "plan_id", "case_id", "quantity", "budget_minor"}


def tool_trace(tool, args, result):
    def allowed(source, keys):
        return {
            k: v
            for k, v in source.items()
            if k in keys and isinstance(v, (str, int, bool, type(None)))
        }

    return {"tool": tool, "args": allowed(args, ARGUMENTS), "result": allowed(result, RESULTS)}
