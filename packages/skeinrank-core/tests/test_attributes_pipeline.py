from skeinrank import (
    AttributePack,
    AttributeSlot,
    extract_attributes,
    get_attribute_profile,
    list_attribute_profiles,
)


def test_attribute_profiles_are_listed_and_loadable():
    assert "default_it" in list_attribute_profiles()
    profile = get_attribute_profile("default_it")
    assert profile.profile_id == "default_it"
    assert profile.slot_limits[AttributeSlot.TOOL] >= 1
    assert profile.snapshot.version == "default_it@2026-04-29-v1"
    assert profile.alias_matcher_backend == "aho_corasick"


def test_extract_attributes_applies_aliases_and_regex_rules():
    pack = extract_attributes(
        "K8s api-server crashloop on version 1.28 with kube retry",
        profile="default_it",
        debug=True,
    )
    assert isinstance(pack, AttributePack)
    values_by_slot = {(item.slot, item.value) for item in pack.attributes}
    assert (AttributeSlot.TOOL, "kubernetes") in values_by_slot
    assert (AttributeSlot.COMPONENT, "api-server") in values_by_slot
    assert (AttributeSlot.ERROR, "crashloopbackoff") in values_by_slot
    assert (AttributeSlot.VERSION, "1.28") in values_by_slot

    assert pack.passport is not None
    assert any(trace.canonicalized_from == "k8s" for trace in pack.passport.accepted)
    assert any(trace.rule_id == "version_semver" for trace in pack.passport.accepted)


def test_extract_attributes_deduplicates_and_filters_generic_error_terms():
    pack = extract_attributes(
        "error issue timeout timeout kube kube",
        profile="default_it",
        debug=True,
    )
    values_by_slot = [(item.slot, item.value) for item in pack.attributes]
    assert values_by_slot.count((AttributeSlot.ERROR, "timeout")) == 1
    assert (AttributeSlot.TOOL, "kubernetes") in values_by_slot

    assert pack.passport is not None
    filtered_reasons = {trace.reason for trace in pack.passport.filtered_out}
    assert "slot_stopword:ERROR" in filtered_reasons
    assert "duplicate" in filtered_reasons


def test_default_passport_omits_inactive_model_stage_statuses():
    pack = extract_attributes("kube timeout", profile="default_it", debug=True)

    assert pack.passport is not None
    assert pack.passport.stage_status == []
