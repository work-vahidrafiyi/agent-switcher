from urllib.request import Request

import pytest

from agent_switcher.core.proxy import ProxyConfig, ProxyConfigError, load_proxy_config


def test_no_proxy_forces_direct_http_and_clears_inherited_proxy_environment():
    config = ProxyConfig()

    assert config.proxies() == {}
    assert config.subprocess_environment(
        {
            "HTTP_PROXY": "http://inherited.test:8080",
            "https_proxy": "http://inherited.test:8080",
            "NO_PROXY": "localhost",
            "KEEP_ME": "yes",
        }
    ) == {
        "KEEP_ME": "yes",
        "NO_PROXY": "*",
        "no_proxy": "*",
    }


def test_custom_http_proxy_is_used_for_http_https_and_subprocesses():
    config = ProxyConfig.from_values("custom", "http://user:pass@proxy.test:3128")

    assert config.proxies() == {
        "http": "http://user:pass@proxy.test:3128",
        "https": "http://user:pass@proxy.test:3128",
    }
    environment = config.subprocess_environment({"NO_PROXY": "chatgpt.com", "KEEP_ME": "yes"})
    assert environment["HTTP_PROXY"] == config.url
    assert environment["HTTPS_PROXY"] == config.url
    assert environment["http_proxy"] == config.url
    assert environment["https_proxy"] == config.url
    assert environment["KEEP_ME"] == "yes"
    assert "NO_PROXY" not in environment
    assert "no_proxy" not in environment


@pytest.mark.parametrize(
    "value",
    ["", "proxy.test:8080", "socks5://proxy.test:1080", "http://proxy.test:99999", "http://proxy.test/path"],
)
def test_custom_http_proxy_rejects_invalid_urls(value):
    with pytest.raises(ProxyConfigError):
        ProxyConfig.from_values("custom", value)


def test_proxy_transport_builds_an_explicit_proxy_handler(monkeypatch):
    captured = {}

    class Opener:
        def open(self, request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return "response"

    def fake_build_opener(handler):
        captured["proxies"] = handler.proxies
        return Opener()

    monkeypatch.setattr("agent_switcher.core.proxy.build_opener", fake_build_opener)
    config = ProxyConfig.from_values("custom", "http://proxy.test:8080")
    request = Request("https://example.test")

    assert config.open(request, 5.0) == "response"
    assert captured == {
        "proxies": {"http": config.url, "https": config.url},
        "request": request,
        "timeout": 5.0,
    }


def test_load_proxy_config_reads_saved_app_setting_and_falls_back_safely(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        '{"proxy_mode":"custom","proxy_url":"http://proxy.test:8080"}',
        encoding="utf-8",
    )

    assert load_proxy_config(settings_path) == ProxyConfig(
        mode="custom",
        url="http://proxy.test:8080",
    )

    settings_path.write_text('{"proxy_mode":"custom","proxy_url":"invalid"}', encoding="utf-8")
    assert load_proxy_config(settings_path) == ProxyConfig()
