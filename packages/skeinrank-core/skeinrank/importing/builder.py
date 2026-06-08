"""Build SkeinRank dictionaries from parsed import mappings."""

from __future__ import annotations

from collections import defaultdict

from skeinrank.sdk import Dictionary, DictionaryAlias, DictionaryTerm

from .models import ImportWarning, RawMapping

DEFAULT_IMPORTED_SLOT = "TERM"


def build_dictionary(
    mappings: list[RawMapping],
    *,
    name: str = "imported",
) -> tuple[Dictionary | None, list[ImportWarning]]:
    """Build a dictionary candidate and import warnings from raw mappings."""

    warnings: list[ImportWarning] = []
    grouped: dict[str, set[str]] = defaultdict(set)
    slots: dict[str, str] = {}
    alias_owners: dict[str, set[str]] = defaultdict(set)
    seen_pairs: set[tuple[str, str]] = set()

    for mapping in mappings:
        canonical = _clean(mapping.canonical)
        alias = _clean(mapping.alias)
        if not canonical or not alias:
            warnings.append(
                ImportWarning.warn(
                    code="build.empty_mapping",
                    message="Skipped mapping with empty canonical or alias value.",
                    line=mapping.source_line,
                    source="build",
                )
            )
            continue

        if canonical.casefold() == alias.casefold():
            warnings.append(
                ImportWarning.warn(
                    code="build.alias_equals_canonical",
                    message=f"Alias '{alias}' equals canonical '{canonical}'; skipped.",
                    line=mapping.source_line,
                    source="build",
                )
            )
            continue

        pair = (canonical.casefold(), alias.casefold())
        if pair in seen_pairs:
            warnings.append(
                ImportWarning.info(
                    code="build.duplicate_mapping",
                    message=f"Duplicate mapping '{alias}' -> '{canonical}' skipped.",
                    line=mapping.source_line,
                    source="build",
                )
            )
            continue
        seen_pairs.add(pair)

        grouped[canonical].add(alias)
        alias_owners[alias.casefold()].add(canonical)
        if mapping.slot and canonical not in slots:
            slots[canonical] = _normalize_slot(mapping.slot)

    for alias, owners in sorted(alias_owners.items()):
        if len(owners) > 1:
            warnings.append(
                ImportWarning.warn(
                    code="build.alias_collision",
                    message=(
                        f"Alias '{alias}' maps to multiple canonicals: "
                        f"{sorted(owners)}. Review before runtime use."
                    ),
                    source="build",
                )
            )

    if not grouped:
        warnings.append(
            ImportWarning.fatal(
                code="build.empty",
                message="No usable canonical-to-alias mappings were produced.",
                source="build",
            )
        )
        return None, warnings

    terms = [
        DictionaryTerm(
            canonical_value=canonical,
            slot=slots.get(canonical, DEFAULT_IMPORTED_SLOT),
            aliases=[DictionaryAlias(value=alias) for alias in sorted(aliases)],
        )
        for canonical, aliases in sorted(
            grouped.items(), key=lambda item: item[0].casefold()
        )
    ]
    dictionary = Dictionary(profile_name=name, terms=terms)
    return dictionary, warnings


def _clean(value: str) -> str:
    return " ".join(value.strip().split())


def _normalize_slot(value: str) -> str:
    cleaned = "_".join(value.strip().upper().replace("-", "_").split())
    return cleaned or DEFAULT_IMPORTED_SLOT
