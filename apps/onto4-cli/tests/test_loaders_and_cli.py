from pathlib import Path

from onto4.cli.main import main
from onto4.pipeline.loaders import load_context, load_formalization
from onto4.core import Verdict, evaluate


ROOT = Path(__file__).parents[1]


def test_example_profiles_load_and_evaluate():
    expression = load_formalization(ROOT / "examples/formalizations/has_mass_integer_7.yaml")
    context = load_context(ROOT / "profiles/contexts/physical_objects.yaml")

    assert evaluate(expression, context).verdict is Verdict.C


def test_truth_and_evidence_load_as_separate_axes():
    expression = load_formalization(ROOT / "examples/formalizations/has_mass_car.yaml")
    context = load_context(ROOT / "profiles/contexts/verified_physical_objects.yaml")

    result = evaluate(expression, context)

    assert result.verdict is Verdict.T
    assert result.evidence.value == "TrueOnly"


def test_compare_command_emits_all_contexts(capsys):
    code = main(
        [
            "compare",
            str(ROOT / "examples/formalizations/identity_substance.yaml"),
            "--context",
            str(ROOT / "profiles/contexts/process.yaml"),
            "--context",
            str(ROOT / "profiles/contexts/substance.yaml"),
        ]
    )

    output = capsys.readouterr().out
    assert code == 0
    assert "process" in output
    assert "substance" in output
    assert "Onto4: C" in output
    assert "Onto4: U" in output


def test_json_renderer_handles_uncomputed_evidence(capsys):
    code = main(
        [
            "eval",
            str(ROOT / "examples/formalizations/has_mass_integer_7.yaml"),
            "--context",
            str(ROOT / "profiles/contexts/physical_objects.yaml"),
            "--format",
            "json",
        ]
    )

    output = capsys.readouterr().out
    assert code == 0
    assert '"verdict": "C"' in output
    assert '"evidence": null' in output
