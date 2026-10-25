# PR #57 — deterministic target-binding conformance gate

Gate выполняется без модели и проверяет существующие host-owned semantic
binding validators. В него входят exact preservation, reorder, missing/unknown
ID, catalog-valid wrong ID, wrong object, stale lineage, structural resolution,
unsupported relation и duplicate claims.

`offline_gate_passed=true` означает только conformance схемы, каталога,
lineage и transition. Semantic correctness остаётся `not_evaluated`: catalog
valid target ID не доказывает сохранение смысла.

Live run не выполнялся до независимого review этого gate.
