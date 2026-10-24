import httpx
import pytest

from app.core.config import Settings
from app.operations.client import SimulationClient


@pytest.mark.parametrize(
    "status,content",
    [
        (409, '{"error":{"code":"ACTION_CONTENT_CONFLICT"}}'),
        (200, "not json"),
        (200, "null"),
        (200, '{"quantity":NaN}'),
    ],
)
async def test_purchase_protocol_evidence_is_preserved(status, content):
    client = SimulationClient(
        Settings(_env_file=None, simulation_token="unit-simulator-credential-00000001"),
        transport=httpx.MockTransport(lambda r: httpx.Response(status, text=content)),
    )
    result = await client.purchase("action-one", {})
    assert result == (
        {"error": {"code": "ACTION_CONTENT_CONFLICT"}}
        if status == 409
        else {"http_status": 200, "raw_body": content}
    )
    assert await client.get_purchase("action-one") == result
