# PR #56 — Frozen target-binding diagnostic protocol

Это research-only protocol для выяснения причины потери target identity в
schema-valid refinement. Внутри одной пары фиксируются один host-issued
question, один scripted answer, один initial snapshot и одна semantic target
family. Сравниваются только refinement protocols; clarification policy не
является независимой переменной.

Условия:

- A — Full Snapshot без binding claim;
- B — Explicit Binding с host-owned target catalog;
- C — минимальный target-focused envelope с binding claim.

Используются два существующих frozen сценария: genome identity и intrinsic
present. Manifest публикует только безопасные aliases, digests, schema и
разрешённые claim relations. Semantic correctness остаётся `not_evaluated`.
Live run не выполнялся.
