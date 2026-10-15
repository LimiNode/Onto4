"""Loader and validation for the hidden clarification evaluation corpus."""

from __future__ import annotations

from dataclasses import dataclass
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

    def public_input(self) -> dict[str, str]:
        """Return only fields allowed in a model-facing evaluation request."""

        result = {"utterance": self.utterance}
        if self.context is not None:
            result["context"] = self.context
        return result


@dataclass(frozen=True)
class ClarificationCorpus:
    version: int
    name: str
    cases: tuple[ClarificationCorpusCase, ...]


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
    raw_cases = root.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("corpus.cases must be a non-empty array.")

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
        cases.append(
            ClarificationCorpusCase(
                case_id=case_id,
                utterance=utterance,
                context=context,
                hidden_interpretation=hidden_interpretation,
                expected_clarification=expected_clarification,
                expected_after_answer=expected_after_answer,
            )
        )
    return ClarificationCorpus(version=version, name=name, cases=tuple(cases))


__all__ = ["ClarificationCorpus", "ClarificationCorpusCase", "load_clarification_corpus"]
