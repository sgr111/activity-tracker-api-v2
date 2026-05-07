import httpx
from typing import Any


MOCK_GEO_API = "https://httpbin.org/anything"


async def enrich_event(client: httpx.AsyncClient, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Calls an external API via httpx to enrich the event payload.
    In production replace MOCK_GEO_API with a real IP geo service.
    """
    enriched = dict(payload)

    try:
        ip = payload.get("ip")
        if ip:
            res = await client.get(MOCK_GEO_API, params={"ip": ip}, timeout=3.0)
            if res.status_code == 200:
                enriched["enriched"]           = True
                enriched["enrichment_source"]  = "httpbin_mock"
    except httpx.TimeoutException:
        enriched["enriched"]          = False
        enriched["enrichment_error"]  = "timeout"
    except httpx.RequestError:
        enriched["enriched"]          = False
        enriched["enrichment_error"]  = "request_failed"

    return enriched
