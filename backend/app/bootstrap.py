"""Application composition: scheduling itself has no domain-specific dispatch."""

from app.execution.jobs import make_handlers as execution_handlers
from app.operations.jobs import make_handlers as operations_handlers
from app.planning.jobs import make_handlers as planning_handlers
from app.scheduling.handlers import make_handlers as scheduling_handlers


def make_handlers(settings):
    handlers = {}
    for factory in (
        scheduling_handlers,
        operations_handlers,
        planning_handlers,
        execution_handlers,
    ):
        additions = factory(settings)
        duplicates = handlers.keys() & additions.keys()
        if duplicates:
            raise ValueError(f"Duplicate job handlers: {sorted(duplicates)}")
        handlers.update(additions)
    return handlers
