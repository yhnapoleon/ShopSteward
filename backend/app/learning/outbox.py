from sqlalchemy.dialects.postgresql import insert

from app.core.errors import AppError
from app.core.hashing import digest
from app.learning.models import LearningOutbox, LearningPolicyRow
from app.learning.repository import scope_id
from app.learning.schemas import LearningEvent


async def append(session, *, scope, event):
    event = LearningEvent.model_validate(event)
    # Serialize collection with consent changes, including requests already in flight.
    pol = await session.get(
        LearningPolicyRow, scope_id(scope), with_for_update=True, populate_existing=True
    )
    # Collection only follows a durable explicit consent. Do not create preferences here.
    if not pol or pol.mode == "off" or not pol.enabled_at or event.available_at < pol.enabled_at:
        return None
    document = event.model_dump(mode="json")
    identifier = digest(
        [
            pol.id,
            pol.version,
            event.source_kind,
            event.source_id,
            event.source_version,
            event.event_type,
        ]
    )
    content = digest(document)
    await session.execute(
        insert(LearningOutbox)
        .values(
            id=identifier,
            scope_id=pol.id,
            policy_version=pol.version,
            digest=content,
            document=document,
            processed=False,
        )
        .on_conflict_do_nothing()
    )
    row = await session.get(LearningOutbox, identifier)
    if row.digest != content:
        raise AppError(409, "LEARNING_EVENT_CONFLICT", "Source version changed its content")
    return identifier
