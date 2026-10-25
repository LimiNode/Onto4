# PR #53 — corrective bounded live pilot

Этот receipt является отдельным bounded run после исправления runner. Исторический
`pr53-live-pilot-20261025.json` не изменялся.

- source SHA: `495ea38`
- run id: `pr53-bounded-20261025-corrective-v2`
- protocol: `pr40-full-snapshot-v1`
- conditions: `A`, затем `B`
- cases: 2; максимум 3 хода на условие
- model artifact digest: `null` (endpoint его не предоставляет)

Обе frozen obligations из PR #51 реально применялись по номеру хода. Для обоих
сценариев все четыре вызова были schema/provenance-valid и выдали вопрос с
подтверждёнными target family/target ID. Однако target identity терялась уже
после первого перехода в обеих условиях. Поэтому пары имеют статус
`initial_matched_continuation_not_comparable`, а не успешное multi-turn
сравнение.

| Сценарий | A | B | Pair |
| --- | --- | --- | --- |
| genome identity | 1 ход, `unverified_retarget` | 1 ход, `unverified_retarget` | `initial_matched_continuation_not_comparable` |
| intrinsic present | 1 ход, `unverified_retarget` | 1 ход, `unverified_retarget` | `initial_matched_continuation_not_comparable` |

В обоих случаях наблюдался structural churn без structural reduction. Это
операционное наблюдение о потере подтверждённой target continuity, а не
semantic verdict. Независимый semantic oracle отсутствует; semantic result
остаётся `not_evaluated`, aggregate verdict — `not_comparable`.

Сырые prompts, ответы, target IDs и payloads не публиковались. Новый запуск не
повторялся ради благоприятного результата.
