import httpx
from typing import Optional
from core.config import settings

class TextService:
    http_client: Optional[httpx.AsyncClient] = None

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        if cls.http_client is None:
            cls.http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.LANGUAGETOOL_TIMEOUT),
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
            )
        return cls.http_client

    @classmethod
    async def close_client(cls):
        if cls.http_client is not None:
            await cls.http_client.aclose()
            cls.http_client = None

text_service = TextService()
