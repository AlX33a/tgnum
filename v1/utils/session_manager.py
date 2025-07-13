#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import random
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from utils.logging_cfg import setup_logger

class SessionManager:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.logger = setup_logger("session_manager", cfg["log_level"])
        self.session = self._create_base_session()

    def _create_base_session(self) -> requests.Session:
        retry = Retry(
            total=self.cfg["retry_total"],
            backoff_factor=self.cfg["retry_backoff_factor"],
            status_forcelist=[403, 429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
            raise_on_status=False
        )
        sess = requests.Session()
        adapter = HTTPAdapter(max_retries=retry)
        sess.mount("http://", adapter)
        sess.mount("https://", adapter)
        return sess

    def _get_headers(self) -> dict:
        ua = random.choice(self.cfg["user_agents"])
        return {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "DNT": "1",
            "Connection": "keep-alive"
        }

    def _get_proxy(self) -> dict:
        if not self.cfg.get("enable_proxy", False):
            return {}
        up, pw = self.cfg["proxy_username"], self.cfg["proxy_password"]
        host, port = self.cfg["proxy_host"], self.cfg["proxy_port"]
        url = f"http://{up}:{pw}@{host}:{port}"
        return {"http": url, "https": url}

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        headers = self._get_headers()
        kwargs.setdefault("headers", headers)
        kwargs.setdefault("timeout", (self.cfg["connect_timeout"], self.cfg["read_timeout"]))
        if self.cfg.get("enable_proxy", False):
            kwargs["proxies"] = self._get_proxy()
        self.logger.debug(f"{method} {url} via proxy {kwargs.get('proxies')}")
        return self.session.request(method, url, **kwargs)

    def get(self, url: str, **kwargs) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        return self.request("POST", url, **kwargs)
