from pathlib import Path


def test_synthesis_keeps_protocol_and_semantics_separate():
    report = " ".join(
        (Path(__file__).parents[3] / "docs" / "reports" / "pr59-binding-synthesis.md")
        .read_text(encoding="utf-8")
        .split()
    )
    assert "literal target retained" in report
    assert "semantic correctness" in report
    assert "not semantically comparable" in report
    assert "semantic adjudication receipt" in report
