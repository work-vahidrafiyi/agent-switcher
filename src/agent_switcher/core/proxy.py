from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, Optional
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener
from urllib.error import HTTPError, URLError


ProxyMode = Literal["none", "custom"]
PROXY_ENV_KEYS = (
    "ALL_PROXY",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "NO_PROXY",
    "all_proxy",
    "https_proxy",
    "http_proxy",
    "no_proxy",
)
TRANSIENT_HTTP_STATUS = {408, 425, 429, 500, 502, 503, 504}
NETWORK_RETRY_DELAYS = (0.35, 1.0)


class ProxyConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ProxyConfig:
    mode: ProxyMode = "none"
    url: str = ""

    @classmethod
    def from_values(cls, mode: object, url: object) -> "ProxyConfig":
        normalized_mode = mode if mode in {"none", "custom"} else "none"
        normalized_url = url.strip() if isinstance(url, str) else ""
        config = cls(mode=normalized_mode, url=normalized_url)
        config.validate()
        return config

    def validate(self) -> None:
        if self.mode == "none":
            return
        if self.mode != "custom":
            raise ProxyConfigError("Unknown proxy mode.")
        if not self.url:
            raise ProxyConfigError("Enter an HTTP proxy URL.")
        try:
            parsed = urlsplit(self.url)
            port = parsed.port
        except ValueError as exc:
            raise ProxyConfigError("Enter a valid HTTP proxy URL.") from exc
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ProxyConfigError("Proxy URL must start with http:// or https://.")
        if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ProxyConfigError("Enter a proxy URL without a path, query, or fragment.")
        if port is not None and not 1 <= port <= 65535:
            raise ProxyConfigError("Proxy port must be between 1 and 65535.")

    def open(self, request: Request, timeout: float):
        handler = ProxyHandler(self.proxies())
        opener = build_opener(handler)
        for attempt in range(len(NETWORK_RETRY_DELAYS) + 1):
            try:
                return opener.open(request, timeout=timeout)
            except HTTPError as exc:
                if exc.code not in TRANSIENT_HTTP_STATUS or attempt >= len(NETWORK_RETRY_DELAYS):
                    raise
                exc.close()
            except (URLError, TimeoutError, socket.timeout, ConnectionError):
                if attempt >= len(NETWORK_RETRY_DELAYS):
                    raise
            time.sleep(NETWORK_RETRY_DELAYS[attempt])
        raise RuntimeError("Network retry loop exited unexpectedly.")

    def proxies(self) -> dict[str, str]:
        if self.mode == "none":
            return {}
        return {"http": self.url, "https": self.url}

    def subprocess_environment(
        self,
        source: Optional[Mapping[str, str]] = None,
        **updates: str,
    ) -> dict[str, str]:
        environment = dict(os.environ if source is None else source)
        for key in PROXY_ENV_KEYS:
            environment.pop(key, None)
        environment.update(updates)
        if self.mode == "none":
            environment.update({"NO_PROXY": "*", "no_proxy": "*"})
        else:
            environment.update(
                {
                    "ALL_PROXY": self.url,
                    "HTTP_PROXY": self.url,
                    "HTTPS_PROXY": self.url,
                    "all_proxy": self.url,
                    "http_proxy": self.url,
                    "https_proxy": self.url,
                }
            )
        return environment


def load_proxy_config(path: Path) -> ProxyConfig:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return ProxyConfig()
    if not isinstance(data, Mapping):
        return ProxyConfig()
    try:
        return ProxyConfig.from_values(data.get("proxy_mode"), data.get("proxy_url"))
    except ProxyConfigError:
        return ProxyConfig()
