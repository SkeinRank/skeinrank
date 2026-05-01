import inspect


def test_torch_bi_encoder_warmup_callable_without_args():
    """Regression: RerankEngine calls scorer.warmup() with no args.

    Torch adapters must accept a zero-arg call to support warmup policies
    like `first_call` and `init`.
    """

    from skeinrank.adapters.torch_bi_encoder import TorchBiEncoderRescorer

    sig = inspect.signature(TorchBiEncoderRescorer.warmup)
    params = list(sig.parameters.values())
    # params[0] is `self`
    assert len(params) >= 1
    # All other parameters must have defaults.
    for p in params[1:]:
        assert p.default is not inspect._empty


def test_torch_bi_encoder_score_signature_matches_engine():
    """Engine calls scorer.score(query, candidates, *, batch_size=...)."""

    from skeinrank.adapters.torch_bi_encoder import TorchBiEncoderRescorer

    sig = inspect.signature(TorchBiEncoderRescorer.score)
    params = list(sig.parameters.values())
    # Expect: self, query, candidates, *, batch_size=...
    assert [p.name for p in params[:3]] == ["self", "query", "candidates"]
    # Ensure query and candidates are positional-or-keyword (not keyword-only).
    assert params[1].kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD,)
    assert params[2].kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD,)
    # batch_size must be keyword-only and optional.
    batch = sig.parameters.get("batch_size")
    assert batch is not None
    assert batch.kind == inspect.Parameter.KEYWORD_ONLY
    assert batch.default is not inspect._empty
