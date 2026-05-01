from skeinrank import (
    AttributeSlot,
    AttributeSnapshot,
    extract_attributes,
    get_attribute_profile,
)
from skeinrank.attributes.alias_map import AliasEntry, AliasMap


def test_default_profile_exposes_snapshot_and_aho_matcher_backend():
    profile = get_attribute_profile("default_it")

    assert isinstance(profile.snapshot, AttributeSnapshot)
    assert profile.snapshot.version == "default_it@2026-04-29-v1"
    assert profile.snapshot.source == "file"
    assert profile.alias_matcher_backend == "aho_corasick"


def test_extract_attributes_returns_snapshot_metadata_and_matcher_backend():
    pack = extract_attributes("kube api timeout", profile="default_it", debug=True)

    assert pack.snapshot is not None
    assert pack.snapshot.version == "default_it@2026-04-29-v1"
    assert pack.alias_matcher_backend == "aho_corasick"
    assert pack.passport is not None
    assert pack.passport.snapshot is not None
    assert pack.passport.snapshot.version == pack.snapshot.version
    assert pack.passport.alias_matcher_backend == "aho_corasick"


def test_aho_corasick_alias_matcher_matches_simple_backend_semantics():
    entries = [
        AliasEntry(
            alias="k8s",
            canonical="kubernetes",
            slot=AttributeSlot.TOOL,
            confidence=0.99,
        ),
        AliasEntry(
            alias="kube",
            canonical="kubernetes",
            slot=AttributeSlot.TOOL,
            confidence=0.97,
        ),
        AliasEntry(
            alias="pg", canonical="postgresql", slot=AttributeSlot.DB, confidence=0.91
        ),
    ]
    text = "k8s kube upgrade pg"

    simple = AliasMap(entries, matcher_backend="simple")
    aho = AliasMap(entries, matcher_backend="aho_corasick")

    simple_matches = [
        (item.slot, item.canonical, item.alias, item.start, item.end)
        for item in simple.find(text)
    ]
    aho_matches = [
        (item.slot, item.canonical, item.alias, item.start, item.end)
        for item in aho.find(text)
    ]

    assert aho.matcher_backend == "aho_corasick"
    assert aho_matches == simple_matches
    assert (AttributeSlot.DB, "postgresql", "pg", 17, 19) in aho_matches


def test_aho_corasick_respects_word_boundaries_for_short_aliases():
    entries = [
        AliasEntry(
            alias="pg", canonical="postgresql", slot=AttributeSlot.DB, confidence=0.91
        )
    ]
    matcher = AliasMap(entries, matcher_backend="aho_corasick")

    assert matcher.find("pg latency")
    assert matcher.find("upgrade") == []
