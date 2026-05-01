from skeinrank import (
    AttributeModelAdapters,
    AttributeSlot,
    FailingAdapter,
    ModelCandidate,
    StaticE5Adapter,
    StaticGLiNERAdapter,
    StaticKeyBERTAdapter,
    extract_attributes,
)


def test_extract_attributes_accepts_optional_model_adapters():
    adapters = AttributeModelAdapters(
        gliner=StaticGLiNERAdapter(
            [
                ModelCandidate(
                    slot=AttributeSlot.TOOL,
                    value="Kubernetes",
                    source="gliner",
                    matched_text="Kubernetes",
                    confidence=0.88,
                )
            ]
        ),
        e5=StaticE5Adapter(
            [
                ModelCandidate(
                    slot=AttributeSlot.COMPONENT,
                    value="api-server",
                    source="e5",
                    matched_text="control plane",
                    confidence=0.81,
                )
            ]
        ),
        keybert=StaticKeyBERTAdapter(
            [
                ModelCandidate(
                    slot=AttributeSlot.COMPONENT,
                    value="retry-budget",
                    source="keybert",
                    matched_text="retry budget",
                    confidence=0.79,
                )
            ]
        ),
    )

    pack = extract_attributes(
        "Kubernetes control plane hit retry budget",
        debug=True,
        adapters=adapters,
        use_gliner=True,
        use_e5=True,
        use_keybert=True,
    )

    values_by_slot = {(item.slot, item.value, item.source) for item in pack.attributes}
    assert (AttributeSlot.TOOL, "kubernetes", "gliner") in values_by_slot
    assert (AttributeSlot.COMPONENT, "api-server", "e5") in values_by_slot
    assert (AttributeSlot.COMPONENT, "retry-budget", "keybert") in values_by_slot
    assert pack.passport is not None
    assert all(status.executed for status in pack.passport.stage_status)


def test_extract_attributes_gracefully_falls_back_when_adapters_are_missing():
    pack = extract_attributes(
        "k8s timeout on version 1.29",
        debug=True,
        use_gliner=True,
        use_e5=True,
        use_keybert=True,
    )
    values_by_slot = {(item.slot, item.value) for item in pack.attributes}
    assert (AttributeSlot.TOOL, "kubernetes") in values_by_slot
    assert (AttributeSlot.ERROR, "timeout") in values_by_slot
    assert (AttributeSlot.VERSION, "1.29") in values_by_slot
    assert pack.passport is not None
    assert {status.warning for status in pack.passport.stage_status} == {
        "gliner_adapter_unavailable",
        "e5_adapter_unavailable",
        "keybert_adapter_unavailable",
    }


def test_extract_attributes_handles_adapter_failure_without_breaking_pipeline():
    adapters = AttributeModelAdapters(gliner=FailingAdapter("gliner_boom"))
    pack = extract_attributes(
        "kube crashloop",
        debug=True,
        adapters=adapters,
        use_gliner=True,
    )
    values_by_slot = {(item.slot, item.value) for item in pack.attributes}
    assert (AttributeSlot.TOOL, "kubernetes") in values_by_slot
    assert (AttributeSlot.ERROR, "crashloopbackoff") in values_by_slot
    assert pack.passport is not None
    warnings = set(pack.passport.warnings)
    assert any(item.startswith("gliner_stage_failed:gliner_boom") for item in warnings)
    gliner_status = next(
        status for status in pack.passport.stage_status if status.stage == "gliner"
    )
    assert gliner_status.executed is False
    assert gliner_status.warning == "gliner_stage_failed:gliner_boom"
