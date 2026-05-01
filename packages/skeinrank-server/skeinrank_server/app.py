from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from . import core_adapter as core_adapter_mod
from . import es_client as es_client_mod
from .config import ServerConfig
from .models import (
    AttributeExtractRequest,
    AttributeExtractResponse,
    DiagnosticsResponse,
    ExtractedAttributeModel,
    HealthzResponse,
    RankedItem,
    RerankESRequest,
    RerankESResponse,
)
from .telemetry import make_logger


def create_app(cfg: ServerConfig) -> FastAPI:
    app = FastAPI(title="skeinrank-server", version="0.1.0")

    logger = make_logger(cfg.telemetry)
    # Module-level indirection keeps create_app testable: tests can monkeypatch
    # `skeinrank_server.es_client.ESClient` and `skeinrank_server.core_adapter.CoreAdapter`.
    es = es_client_mod.ESClient(cfg.es_url, timeout_s=cfg.es_timeout_s)

    @app.get("/healthz", response_model=HealthzResponse)
    def healthz():
        ok, err = es.ping()
        payload = HealthzResponse(
            status="ok" if ok else "degraded",
            service={"name": "skeinrank-server", "version": "0.1.0"},
            elasticsearch={"ok": ok, "error": err},
        )
        return JSONResponse(payload.model_dump())

    @app.get("/diagnostics", response_model=DiagnosticsResponse)
    def diagnostics():
        ok, err = es.ping()
        core_diag: Optional[dict[str, Any]] = None
        try:
            core = core_adapter_mod.CoreAdapter()
            core_diag = core.diagnostics()
        except Exception:
            core_diag = None
        payload = DiagnosticsResponse(
            config={
                "es_url": cfg.es_url,
                "es_default_index": cfg.es_default_index,
                "es_text_field": cfg.es_text_field,
                "es_query_fields": cfg.es_query_fields,
                "default_profile": cfg.default_profile,
                "default_attribute_profile": cfg.default_attribute_profile,
                "default_passport": cfg.default_passport,
                "telemetry": cfg.telemetry,
            },
            core=core_diag,
            elasticsearch={"ok": ok, "error": err},
        )
        return JSONResponse(payload.model_dump())

    @app.post("/v1/attributes/extract", response_model=AttributeExtractResponse)
    def extract_attributes(req: AttributeExtractRequest):
        request_id = str(uuid.uuid4())
        profile = req.profile or cfg.default_attribute_profile

        try:
            core = core_adapter_mod.CoreAdapter()
            out = core.extract_attributes(
                text=req.text,
                profile=profile,
                debug=req.debug,
                use_gliner=req.use_gliner,
                use_e5=req.use_e5,
                use_keybert=req.use_keybert,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Core error: {type(e).__name__}: {e}"
            )

        resp = AttributeExtractResponse(
            request_id=request_id,
            profile=out.profile_id,
            attributes=[ExtractedAttributeModel(**item) for item in out.attributes],
            passport=out.passport,
        )
        return JSONResponse(resp.model_dump())

    @app.post("/v1/rerank/es", response_model=RerankESResponse)
    def rerank_es(req: RerankESRequest):
        request_id = str(uuid.uuid4())
        t0 = time.perf_counter()

        index = req.index or cfg.es_default_index
        profile = req.profile or cfg.default_profile
        passport = (req.passport or cfg.default_passport).lower()

        # 1) Retrieve BM25 from ES
        try:
            hits = es.search(
                index=index,
                query=req.query,
                k=req.bm25_k,
                query_fields=cfg.es_query_fields,
                text_field=cfg.es_text_field,
                fetch_fields=[cfg.es_text_field],
            )
        except Exception as e:
            raise HTTPException(
                status_code=502, detail=f"Elasticsearch error: {type(e).__name__}: {e}"
            )

        # 2) Rerank via core
        try:
            core = core_adapter_mod.CoreAdapter()
            out = core.rerank(
                profile=profile,
                query=req.query,
                candidates=[{"id": h["id"], "text": h["text"]} for h in hits],
                top_k=req.top_k,
                passport=passport,
                warmup=False,
                batch_size=req.batch_size,
            )
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Core error: {type(e).__name__}: {e}"
            )

        ranked = [
            RankedItem(id=str(x["id"]), score=float(x["score"])) for x in out.ranked
        ]
        wall_ms = (time.perf_counter() - t0) * 1000.0

        # Telemetry (stdout JSONL)
        if logger is not None:
            pp = out.passport or {}
            logger.log(
                {
                    "ts": int(time.time() * 1000),
                    "request_id": request_id,
                    "route": "/v1/rerank/es",
                    "index": index,
                    "bm25_k": int(req.bm25_k),
                    "top_k": int(req.top_k),
                    "profile": profile,
                    "passport": passport,
                    "wall_ms": round(wall_ms, 3),
                    "warnings": pp.get("warnings") or [],
                    "passport_level": pp.get("passport_level"),
                    "passport_upgraded_by": pp.get("passport_upgraded_by"),
                }
            )

        resp = RerankESResponse(
            request_id=request_id,
            profile=profile,
            index=index,
            bm25_k=req.bm25_k,
            top_k=req.top_k,
            results=ranked,
            passport=out.passport,
        )
        return JSONResponse(resp.model_dump())

    return app
