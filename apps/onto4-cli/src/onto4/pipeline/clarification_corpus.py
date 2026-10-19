"""Loader and validation for the hidden clarification evaluation corpus."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml


@dataclass(frozen=True)
class ClarificationCorpusCase:
    case_id: str
    utterance: str
    context: str | None
    hidden_interpretation: Mapping[str, Any] | None
    expected_clarification: Mapping[str, Any] | None
    expected_after_answer: Mapping[str, Any]
    model_input: str = "utterance_only"
    mode: str = "single_pass"
    evaluation_class: str = "unspecified"
    dialogue: tuple[Mapping[str, Any], ...] = ()

    def public_input(self) -> dict[str, str]:
        """Return only fields allowed in a model-facing evaluation request."""

        result = {"utterance": self.utterance}
        if self.model_input == "contextual" and self.context is not None:
            result["context"] = self.context
        return result


@dataclass(frozen=True)
class ClarificationCorpus:
    version: int
    name: str
    cases: tuple[ClarificationCorpusCase, ...]
    model_input: str = "utterance_only"
    context_profiles: Mapping[str, str] = field(default_factory=dict)


def load_semantic_target_catalog(
    path: str | Path,
) -> tuple[int, dict[str, dict[str, dict[str, str]]]]:
    """Load public host targets without reading clarification oracle fields."""

    source = Path(path)
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Unable to load semantic target catalog {source}.") from exc
    root = _mapping(data, "target_catalog")
    version = root.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("target_catalog.version must be a positive integer.")
    raw_cases = root.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("target_catalog.cases must be an array.")
    result: dict[str, dict[str, dict[str, str]]] = {}
    for case_index, raw_case in enumerate(raw_cases):
        case = _mapping(raw_case, f"target_catalog.cases[{case_index}]")
        case_id = case.get("case_id")
        targets = case.get("targets")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("Target catalog case_id must be a non-empty string.")
        if case_id in result:
            raise ValueError(f"Duplicate target catalog case_id: {case_id!r}.")
        if not isinstance(targets, list):
            raise ValueError(f"Target catalog targets for {case_id!r} must be an array.")
        case_targets: dict[str, dict[str, str]] = {}
        for target_index, raw_target in enumerate(targets):
            target = _mapping(
                raw_target,
                f"target_catalog.cases[{case_index}].targets[{target_index}]",
            )
            unknown = set(target) - {"id", "kind", "description"}
            if unknown:
                raise ValueError(f"Unknown public target fields: {sorted(unknown)!r}.")
            target_id = target.get("id")
            kind = target.get("kind")
            description = target.get("description")
            if not isinstance(target_id, str) or not target_id.strip():
                raise ValueError("Public target id must be a non-empty string.")
            if kind not in {"Meaning", "Ontology"}:
                raise ValueError("Public target kind must be Meaning or Ontology.")
            if not isinstance(description, str) or not description.strip():
                raise ValueError("Public target description must be non-empty.")
            if target_id in case_targets:
                raise ValueError(
                    f"Duplicate public target id {target_id!r} in case {case_id!r}."
                )
            case_targets[target_id] = {
                "kind": kind,
                "description": description,
            }
        result[case_id] = case_targets
    return version, result


def semantic_target_catalog_digest(path: str | Path) -> str:
    """Return the exact SHA-256 digest of a public target catalog artifact."""

    try:
        payload = Path(path).read_bytes()
    except OSError as exc:
        raise ValueError(f"Unable to read semantic target catalog {path}.") from exc
    return hashlib.sha256(payload).hexdigest()


def host_semantic_target_bindings(
    corpus: ClarificationCorpus,
) -> dict[tuple[str, str], str]:
    """Extract explicit host-owned target bindings from scripted dialogue.

    The dialogue script is corpus-owned data, while ``Ambiguity.term`` is
    model-produced wording.  A target id may be reused only when the corpus
    assigns it the same semantic family every time; contradictory assignments
    are rejected before a provider is called.
    """

    bindings: dict[tuple[str, str], str] = {}
    for case in corpus.cases:
        for turn in case.dialogue:
            if turn.get("role") != "assistant" or "target_family" not in turn:
                continue
            family = turn.get("target_family")
            target_ids = turn.get("target_ids", ())
            if not isinstance(family, str) or not family.strip():
                raise ValueError("Scripted target_family must be a non-empty string.")
            if not isinstance(target_ids, (list, tuple)) or not target_ids:
                raise ValueError(
                    "A scripted target_family requires at least one target_id."
                )
            for target_id in target_ids:
                if not isinstance(target_id, str) or not target_id.strip():
                    raise ValueError("Scripted target_ids must be non-empty strings.")
                key = (case.case_id, target_id)
                previous = bindings.setdefault(key, family)
                if previous != family:
                    raise ValueError(
                        f"Target id {target_id!r} in case {case.case_id!r} has "
                        "contradictory semantic families."
                    )
    return bindings


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be a mapping.")
    return value


def load_clarification_corpus(path: str | Path) -> ClarificationCorpus:
    source = Path(path)
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Unable to load clarification corpus {source}.") from exc
    root = _mapping(data, "corpus")
    version = root.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError("corpus.version must be an integer.")
    name = root.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("corpus.name must be a non-empty string.")
    visibility = root.get("visibility", {})
    if not isinstance(visibility, Mapping):
        raise ValueError("corpus.visibility must be a mapping when supplied.")
    model_input = visibility.get("model_input", "utterance_only")
    if not isinstance(model_input, str) or model_input not in {
        "utterance_only",
        "contextual",
    }:
        raise ValueError(
            "corpus.visibility.model_input must be 'utterance_only' or 'contextual'."
        )
    raw_cases = root.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("corpus.cases must be a non-empty array.")
    raw_profiles = root.get("context_profiles", {})
    if not isinstance(raw_profiles, Mapping):
        raise ValueError("corpus.context_profiles must be a mapping when supplied.")
    context_profiles: dict[str, str] = {}
    for profile_id, description in raw_profiles.items():
        if not isinstance(profile_id, str) or not profile_id.strip():
            raise ValueError("context_profiles keys must be non-empty strings.")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(
                f"context_profiles[{profile_id!r}] must be a non-empty description."
            )
        context_profiles[profile_id] = description

    cases: list[ClarificationCorpusCase] = []
    seen_ids: set[str] = set()
    for index, raw_case in enumerate(raw_cases):
        item = _mapping(raw_case, f"cases[{index}]")
        case_id = item.get("case_id")
        utterance = item.get("utterance")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"cases[{index}].case_id must be a non-empty string.")
        if case_id in seen_ids:
            raise ValueError(f"Duplicate clarification case_id: {case_id!r}.")
        seen_ids.add(case_id)
        if not isinstance(utterance, str) or not utterance.strip():
            raise ValueError(f"cases[{index}].utterance must be a non-empty string.")
        raw_expected = item.get("expected_clarification")
        if isinstance(raw_expected, str) and raw_expected.lower() == "none":
            expected_clarification = None
        elif raw_expected is None:
            expected_clarification = None
        else:
            expected_clarification = _mapping(
                raw_expected, f"cases[{index}].expected_clarification"
            )
        expected_after_answer = _mapping(
            item.get("expected_after_answer"),
            f"cases[{index}].expected_after_answer",
        )
        hidden = item.get("hidden_interpretation")
        hidden_interpretation = None if hidden is None else _mapping(hidden, f"cases[{index}].hidden_interpretation")
        context = item.get("context")
        if context is not None and (not isinstance(context, str) or not context.strip()):
            raise ValueError(f"cases[{index}].context must be a non-empty string when supplied.")
        if context is not None and context_profiles and context not in context_profiles:
            raise ValueError(
                f"cases[{index}].context {context!r} is not declared in context_profiles."
            )
        case_model_input = item.get("model_input", model_input)
        if not isinstance(case_model_input, str) or case_model_input not in {
            "utterance_only",
            "contextual",
        }:
            raise ValueError(
                f"cases[{index}].model_input must be 'utterance_only' or 'contextual'."
            )
        mode = item.get("mode", "single_pass")
        if mode not in {"single_pass", "dialogue"}:
            raise ValueError(
                f"cases[{index}].mode must be 'single_pass' or 'dialogue'."
            )
        evaluation_class = item.get("evaluation_class", "unspecified")
        if not isinstance(evaluation_class, str) or not evaluation_class.strip():
            raise ValueError(
                f"cases[{index}].evaluation_class must be a non-empty string."
            )
        raw_dialogue = item.get("dialogue", [])
        if raw_dialogue is None:
            raw_dialogue = []
        if not isinstance(raw_dialogue, list):
            raise ValueError(f"cases[{index}].dialogue must be an array.")
        if version < 2:
            dialogue = []
        else:
            dialogue = []
            seen_turn_ids: set[str] = set()
            for turn_index, raw_turn in enumerate(raw_dialogue):
                turn = _mapping(raw_turn, f"cases[{index}].dialogue[{turn_index}]")
                turn_id = turn.get("turn_id")
                role = turn.get("role")
                text = turn.get("text")
                if not isinstance(turn_id, str) or not turn_id.strip():
                    raise ValueError(
                        f"cases[{index}].dialogue[{turn_index}].turn_id must be non-empty."
                    )
                if turn_id in seen_turn_ids:
                    raise ValueError(
                        f"Duplicate dialogue turn_id {turn_id!r} in case {case_id!r}."
                    )
                seen_turn_ids.add(turn_id)
                if role not in {"user", "assistant"}:
                    raise ValueError(
                        f"cases[{index}].dialogue[{turn_index}].role must be user or assistant."
                    )
                if not isinstance(text, str) or not text.strip():
                    raise ValueError(
                        f"cases[{index}].dialogue[{turn_index}].text must be non-empty."
                    )
                if role == "assistant" and "question_kind" in turn:
                    if turn["question_kind"] not in {
                        "Meaning",
                        "Ontology",
                        "Reference",
                        "Presupposition",
                        "Evidence",
                        "Perspective",
                        "Context",
                        "Formalization",
                    }:
                        raise ValueError(
                            f"cases[{index}].dialogue[{turn_index}].question_kind is invalid."
                        )
                if "target_family" in turn and (
                    not isinstance(turn["target_family"], str)
                    or not turn["target_family"].strip()
                ):
                    raise ValueError(
                        f"cases[{index}].dialogue[{turn_index}].target_family must be non-empty."
                    )
                dialogue.append(dict(turn))
        if isinstance(expected_clarification, Mapping):
            expected_family = expected_clarification.get("target_family")
            if isinstance(expected_family, str) and expected_family.strip():
                scripted_families = tuple(
                    turn.get("target_family")
                    for turn in dialogue
                    if turn.get("role") == "assistant"
                    and isinstance(turn.get("target_family"), str)
                    and turn.get("target_family", "").strip()
                )
                if scripted_families and scripted_families[0] != expected_family:
                    raise ValueError(
                        f"cases[{index}] has contradictory expected and scripted target_family."
                    )
        if version >= 2 and mode == "dialogue" and len(dialogue) < 2:
            raise ValueError(
                f"cases[{index}].dialogue must contain at least two turns."
            )
        cases.append(
            ClarificationCorpusCase(
                case_id=case_id,
                utterance=utterance,
                context=context,
                model_input=case_model_input,
                hidden_interpretation=hidden_interpretation,
                expected_clarification=expected_clarification,
                expected_after_answer=expected_after_answer,
                mode=mode,
                evaluation_class=evaluation_class,
                dialogue=tuple(dialogue),
            )
        )
    return ClarificationCorpus(
        version=version,
        name=name,
        cases=tuple(cases),
        model_input=model_input,
        context_profiles=context_profiles,
    )


__all__ = [
    "ClarificationCorpus",
    "ClarificationCorpusCase",
    "host_semantic_target_bindings",
    "load_semantic_target_catalog",
    "load_clarification_corpus",
]
