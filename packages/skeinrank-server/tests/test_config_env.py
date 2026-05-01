from skeinrank_server.config import ServerConfig


def test_server_config_prefers_skeinrank_env(monkeypatch):
    monkeypatch.setenv("SKEINRANK_ES_URL", "http://skeinrank-es:9200")
    monkeypatch.setenv("SKEINRANK_ES_INDEX", "docs")
    monkeypatch.setenv("SKEINRANK_ES_TEXT_FIELD", "body")
    monkeypatch.setenv("SKEINRANK_ES_QUERY_FIELDS", "body,title")
    monkeypatch.setenv("SKEINRANK_ES_TIMEOUT_S", "9")
    monkeypatch.setenv("SKEINRANK_DEFAULT_PROFILE", "e5_small")
    monkeypatch.setenv("SKEINRANK_DEFAULT_ATTRIBUTE_PROFILE", "ops_docs")
    monkeypatch.setenv("SKEINRANK_DEFAULT_PASSPORT", "debug")
    monkeypatch.setenv("SKEINRANK_TELEMETRY", "off")

    cfg = ServerConfig.from_env()

    assert cfg.es_url == "http://skeinrank-es:9200"
    assert cfg.es_default_index == "docs"
    assert cfg.es_text_field == "body"
    assert cfg.es_query_fields == ["body", "title"]
    assert cfg.es_timeout_s == 9.0
    assert cfg.default_profile == "e5_small"
    assert cfg.default_attribute_profile == "ops_docs"
    assert cfg.default_passport == "debug"
    assert cfg.telemetry == "off"


def test_server_config_supports_backward_compatible_aliases(monkeypatch):
    monkeypatch.delenv("SKEINRANK_ES_URL", raising=False)
    monkeypatch.delenv("SKEINRANK_ES_INDEX", raising=False)
    monkeypatch.delenv("SKEINRANK_ES_TEXT_FIELD", raising=False)
    monkeypatch.delenv("SKEINRANK_ES_QUERY_FIELDS", raising=False)
    monkeypatch.delenv("SKEINRANK_ES_TIMEOUT_S", raising=False)

    monkeypatch.setenv("ES_URL", "http://legacy-es:9200")
    monkeypatch.setenv("ES_DEFAULT_INDEX", "legacy-kb")
    monkeypatch.setenv("ES_TEXT_FIELD", "content")
    monkeypatch.setenv("ES_QUERY_FIELDS", "content,title")
    monkeypatch.setenv("ES_TIMEOUT_S", "3")

    cfg = ServerConfig.from_env()

    assert cfg.es_url == "http://legacy-es:9200"
    assert cfg.es_default_index == "legacy-kb"
    assert cfg.es_text_field == "content"
    assert cfg.es_query_fields == ["content", "title"]
    assert cfg.es_timeout_s == 3.0
    assert cfg.default_attribute_profile == "default_it"
