from django.test import AsyncClient


async def test_health_and_interactive_docs_are_served() -> None:
    client = AsyncClient()
    assert (await client.get("/api/health")).json() == {"status": "ok"}
    docs = await client.get("/api/docs")
    assert docs.status_code == 200 and b"openapi.json" in docs.content
