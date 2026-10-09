"""Mission admission is resolved before context selection; no last-N truncation."""

from sqlalchemy import select

from app.agent_bridge.models import AgentRun, Message


def requested_effect(messages):
    # Like memory.change, Agent-specific operations lazily load pure policy;
    # normal API startup does not import the optional model/runtime stack.
    from shopsteward_agent.context.intent import classify_intent

    return classify_intent([{"message_id": str(index), "content": content}
                            for index, content in enumerate(messages)])["requested_effect"]


def admitted_history(rows, *, run_id, conversation_id, input_through_seq, prior_run_ids):
    prior = set(prior_run_ids)
    allowed = [
        row
        for row in rows
        if (row.role == "user" and (row.seq <= input_through_seq or row.run_id == run_id))
        or (row.role == "assistant" and row.run_id in prior)
    ]
    anchors = {}
    for row in allowed:
        key = row.run_id or row.id
        anchors[key] = min(anchors.get(key, row.seq), row.seq)
    allowed.sort(key=lambda row: (anchors[row.run_id or row.id], row.seq))
    return (
        [
            {
                "message_id": row.id,
                "run_id": row.run_id,
                "seq": row.seq,
                "role": row.role,
                "content": row.content,
            }
            for row in allowed
        ],
        {
            "kind": "mission",
            "run_id": run_id,
            "conversation_id": conversation_id,
            "input_through_seq": input_through_seq,
            "admitted_resume_message_ids": [
                row.id for row in allowed if row.role == "user" and row.seq > input_through_seq
            ],
            "prior_run_dependencies": sorted(prior),
        },
    )


async def load_history(session, conversation, run):
    prior = (
        await session.scalars(
            select(AgentRun.id).where(
                AgentRun.conversation_id == conversation.id,
                AgentRun.input_through_seq < run.input_through_seq,
                AgentRun.status == "SUCCEEDED",
            )
        )
    ).all()
    rows = (
        await session.scalars(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                (
                    (Message.role == "user")
                    & ((Message.seq <= run.input_through_seq) | (Message.run_id == run.id))
                )
                | ((Message.role == "assistant") & Message.run_id.in_(prior)),
            )
            .order_by(Message.seq)
        )
    ).all()
    return admitted_history(
        rows,
        run_id=run.id,
        conversation_id=conversation.id,
        input_through_seq=run.input_through_seq,
        prior_run_ids=prior,
    )
