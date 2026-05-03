from skeinrank import (
    AttributeEvidence,
    AttributeModelAdapters,
    AttributePack,
    AttributePassport,
    AttributeProfile,
    AttributeSlot,
    AttributeSnapshot,
    AttributeStageStatus,
    AttributeTrace,
    ExtractedAttribute,
    FailingAdapter,
    ModelCandidate,
    ProfileValidationIssue,
    ProfileValidationReport,
    StaticE5Adapter,
    StaticGLiNERAdapter,
    StaticKeyBERTAdapter,
    build_attribute_profile,
    enrich_documents,
    enrich_jsonl,
    evaluate_demo_queries,
    extract_attributes,
    get_attribute_profile,
    list_attribute_profiles,
    load_attribute_profile,
    load_jsonl,
    validate_attribute_profile,
    write_jsonl,
)


def test_attribute_symbols_are_exported_from_public_api():
    assert AttributeSlot.TOOL.value == "TOOL"
    assert callable(extract_attributes)
    assert callable(get_attribute_profile)
    assert callable(list_attribute_profiles)
    assert callable(build_attribute_profile)
    assert callable(load_attribute_profile)
    assert callable(validate_attribute_profile)
    assert callable(load_jsonl)
    assert callable(write_jsonl)
    assert callable(enrich_documents)
    assert callable(enrich_jsonl)
    assert callable(evaluate_demo_queries)
    assert AttributeEvidence is not None
    assert ExtractedAttribute is not None
    assert AttributeTrace is not None
    assert AttributeProfile is not None
    assert ProfileValidationIssue is not None
    assert ProfileValidationReport is not None
    assert AttributeSnapshot is not None
    assert AttributeStageStatus is not None
    assert AttributePassport is not None
    assert AttributePack is not None
    assert AttributeModelAdapters is not None
    assert ModelCandidate is not None
    assert StaticGLiNERAdapter is not None
    assert StaticE5Adapter is not None
    assert StaticKeyBERTAdapter is not None
    assert FailingAdapter is not None


def test_attribute_pack_contract_keys_are_stable():
    pack = extract_attributes("k8s timeout 1.29", debug=True)
    dumped = pack.model_dump()
    assert set(dumped.keys()) == {
        "text",
        "profile_id",
        "snapshot",
        "alias_matcher_backend",
        "attributes",
        "passport",
    }
    assert set(dumped["attributes"][0].keys()) == {
        "slot",
        "value",
        "source",
        "confidence",
        "evidences",
    }
    assert dumped["passport"] is not None
    assert {
        "schema_version",
        "profile_id",
        "snapshot",
        "alias_matcher_backend",
        "normalized_text",
        "proposed",
        "accepted",
        "filtered_out",
        "warnings",
        "stage_status",
    }.issubset(dumped["passport"].keys())
