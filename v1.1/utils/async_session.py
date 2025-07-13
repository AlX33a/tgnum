# utils/async_session.py

import random
import asyncio  # добавлено для TimeoutError
import aiohttp
from aiohttp_retry import RetryClient, ExponentialRetry
from aiohttp_proxy import ProxyConnector
from utils.config import load_config

cfg = load_config("prod")

class AsyncSession:
    def __init__(self):
        # Настройка прокси (HTTP/SOCKS) при enable_proxy
        connector = None
        if cfg.get("enable_proxy", False):
            proxy_url = (
                f"http://{cfg['proxy_username']}:{cfg['proxy_password']}"
                f"@{cfg['proxy_host']}:{cfg['proxy_port']}"
            )
            connector = ProxyConnector.from_url(proxy_url)

        # Таймауты: подключение и чтение
        timeout = aiohttp.ClientTimeout(
            total=None,
            connect=cfg.get("connect_timeout", 10.0),
            sock_connect=cfg.get("sock_connect_timeout", cfg.get("connect_timeout", 10.0)),
            sock_read=cfg.get("sock_read_timeout", cfg.get("read_timeout", 30.0))
        )

        # Базовый клиент
        client = aiohttp.ClientSession(timeout=timeout, connector=connector)

        # Стратегия ретраев: исключения таймаута и сетевых ошибок
        retry_options = ExponentialRetry(
            attempts=cfg.get("retry_total", 5),
            start_timeout=cfg.get("retry_backoff_factor", 0.5),
            max_timeout=cfg.get("retry_max_timeout", 30.0),
            exceptions={aiohttp.ClientError, asyncio.TimeoutError}
        )
        self._client = RetryClient(
            client_session=client,
            retry_options=retry_options,
            raise_for_status=False
        )

    async def get(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent", random.choice(cfg["user_agents"]))
        proxy = kwargs.pop("proxy", None)
        return await self._client.get(url, headers=headers, proxy=proxy)

    async def post(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent", random.choice(cfg["user_agents"]))
        json_body = kwargs.pop("json", None)
        proxy = kwargs.pop("proxy", None)
        return await self._client.post(url, headers=headers, json=json_body, proxy=proxy)

    async def close(self):
        await self._client.close()
