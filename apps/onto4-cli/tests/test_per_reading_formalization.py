import pytest

from onto4.core import AssessmentContext
from onto4.pipeline.ask import formalize_per_reading_and_context
from onto4.providers import FormalizationRequest
from onto4.reasoning import (
    ConceptualDepth,
    FormalizationCandidate,
    InterpretationSpace,
    SemanticReading,
)


def _space():
    return InterpretationSpace(
        id="space",
        source_text="The door is closed.",
        conceptual_depth=ConceptualDepth.Ordinary,
        readings=(
            SemanticReading("reading-0", "closed", "not open"),
            SemanticReading("reading-1", "locked", "cannot open"),
        ),
    )


class RecordingProvider:
    def __init__(self):
        self.requests = []

    def formalize(self, request: FormalizationRequest):
        self.requests.append(request)
        assert request.reading is not None
        assert request.context_id is not None
        return (
            FormalizationCandidate(
                id=f"{request.reading.id}:{request.context_id}",
                label=request.reading.label,
                formalization_id=f"formal:{request.reading.id}",
                context_id=request.context_id,
                formalization=None,
                reading_id=request.reading.id,
            ),
        )


def test_per_reading_formalization_fans_out_in_stable_order_and_binds_provenance():
    provider = RecordingProvider()
    contexts = {
        "physical_objects": AssessmentContext(),
        "filesystem": AssessmentContext(),
    }

    candidates = formalize_per_reading_and_context(
        _space(), formalization_provider=provider, contexts=contexts
    )

    assert [(request.reading.id, request.context_id) for request in provider.requests] == [
        ("reading-0", "physical_objects"),
        ("reading-0", "filesystem"),
        ("reading-1", "physical_objects"),
        ("reading-1", "filesystem"),
    ]
    assert [(candidate.reading_id, candidate.context_id) for candidate in candidates] == [
        ("reading-0", "physical_objects"),
        ("reading-0", "filesystem"),
        ("reading-1", "physical_objects"),
        ("reading-1", "filesystem"),
    ]


class MismatchingProvider(RecordingProvider):
    def formalize(self, request: FormalizationRequest):
        candidate = super().formalize(request)[0]
        return (
            FormalizationCandidate(
                id=candidate.id,
                label=candidate.label,
                formalization_id=candidate.formalization_id,
                context_id="wrong-context",
                formalization=candidate.formalization,
                reading_id=candidate.reading_id,
            ),
        )


def test_per_reading_formalization_rejects_mismatched_context_provenance():
    with pytest.raises(ValueError, match="context provenance"):
        formalize_per_reading_and_context(
            _space(),
            formalization_provider=MismatchingProvider(),
            contexts={"physical_objects": AssessmentContext()},
        )
