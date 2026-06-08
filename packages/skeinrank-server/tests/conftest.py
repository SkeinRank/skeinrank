import pytest
from fastapi.testclient import TestClient
from skeinrank_server.app import create_app
from skeinrank_server.config import ServerConfig


@pytest.fixture()
def cfg():
    return ServerConfig(
        es_url="http://es:9200",
        es_default_index="kb",
        es_text_field="text",
        es_query_fields=["text", "title"],
        es_timeout_s=1.0,
        default_profile="rerank_auto",
        default_attribute_profile="default_it",
        default_passport="summary",
        telemetry="off",
    )


@pytest.fixture()
def client(cfg, monkeypatch):
    from skeinrank_server import core_adapter as core_mod
    from skeinrank_server import es_client as es_mod

    monkeypatch.setattr(es_mod.ESClient, "ping", lambda self: (True, None))
    monkeypatch.setattr(
        es_mod.ESClient,
        "search",
        lambda self, *, index, query, k, query_fields, text_field, fetch_fields=None: [
            {
                "id": "1",
                "text": "How to reset password in Okta",
                "score": 1.0,
                "source": {text_field: "How to reset password in Okta"},
            },
            {
                "id": "2",
                "text": "Okta admin guide",
                "score": 0.9,
                "source": {text_field: "Okta admin guide"},
            },
        ][: int(k)],
    )

    class FakeCore:
        def __init__(self):
            pass

        def rerank(
            self,
            *,
            profile,
            query,
            candidates,
            top_k,
            passport,
            warmup=False,
            batch_size=None,
        ):
            ranked = [{"id": candidates[0]["id"], "score": 0.99}]
            pp = None
            if passport != "off":
                pp = {
                    "schema_version": "1",
                    "profile_id": profile,
                    "passport_level": passport,
                    "passport_upgraded_by": [],
                    "warnings": [],
                    "stages": [
                        {"name": "score", "elapsed_ms": 1.0, "details": {}},
                        {"name": "sort", "elapsed_ms": 0.1, "details": {}},
                    ],
                    "total_ms": 1.1,
                }
            return core_mod.CoreOutput(ranked=ranked, passport=pp)

        def extract_attributes(
            self,
            *,
            text,
            profile,
            debug=False,
            use_gliner=None,
            use_e5=None,
            use_keybert=None,
        ):
            passport = None
            if debug:
                passport = {
                    "schema_version": "1",
                    "profile_id": profile,
                    "normalized_text": text.lower(),
                    "proposed": [],
                    "accepted": [],
                    "filtered_out": [],
                    "warnings": [],
                }
                stage_status = []
                for stage, enabled in (
                    ("gliner", use_gliner),
                    ("e5", use_e5),
                    ("keybert", use_keybert),
                ):
                    if enabled:
                        stage_status.append(
                            {
                                "stage": stage,
                                "enabled": True,
                                "available": True,
                                "executed": True,
                                "emitted_candidates": 0,
                                "warning": None,
                            }
                        )
                if stage_status:
                    passport["stage_status"] = stage_status
            return core_mod.AttributeCoreOutput(
                profile_id=profile,
                attributes=[
                    {
                        "slot": "TOOL",
                        "value": "kubernetes",
                        "source": "alias",
                        "confidence": 1.0,
                        "evidences": [
                            {
                                "source": "alias",
                                "matched_text": "k8s",
                                "start": 0,
                                "end": 3,
                                "rule_id": None,
                            }
                        ],
                    }
                ],
                passport=passport,
            )

        def diagnostics(self):
            return {
                "runtime": {"backend": "builtin"},
                "available_profiles": ["rerank_auto"],
            }

    monkeypatch.setattr(core_mod, "CoreAdapter", FakeCore)

    app = create_app(cfg)
    return TestClient(app)
