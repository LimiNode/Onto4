# PR #53 — bounded matched live Bonsai pilot

Это один ограниченный live-прогон по frozen contract PR #51 и offline gate PR
#52. Обе ветки используют один и тот же `Full Snapshot` refinement protocol.
Различается только host-side selection policy: A допускает повторный target, B
ведёт bounded ledger уже выданных targets.

## Условия

- два сценария: genome identity и intrinsic present;
- два условия на сценарий: A и B;
- максимум три хода на условие;
- temperature `0`, thinking disabled, `max_output_tokens=1024`;
- порядок условий: A, затем B;
- run id: `pr53-bonsai-20261025-matched-01`;
- provider protocol: `pr40-full-snapshot-v1`;
- model artifact digest: `null` — endpoint его не предоставил.

Артефакт: [pr53-live-pilot-20261025.json](pr53-live-pilot-20261025.json).

## Фактическое наблюдение

Все четыре model-backed refinement calls завершились с валидными successor и
transition provenance. В обоих сценариях и обеих условиях target исчезал уже
после первого хода:

| Сценарий | Условие A | Условие B | Pair |
| --- | --- | --- | --- |
| genome identity | 1 ход, `unverified_retarget` | 1 ход, `unverified_retarget` | `not_comparable` |
| intrinsic present | 1 ход, `unverified_retarget` | 1 ход, `unverified_retarget` | `not_comparable` |

Наблюдался structural churn без structural reduction. Ни одна ветка не
достигла второго вопроса: host не получил подтверждённую непрерывность target.
Это не semantic failure и не доказательство равенства или превосходства
стратегий; semantic oracle отсутствует, поэтому `semantic_identity` остаётся
`not_evaluated`.

## Ограничения и границы

- `pair_comparability` оставлен `not_comparable` для обеих пар;
- raw prompts, answers, target IDs, provider payloads и credentials не
  публиковались;
- production admission и semantic adjudication не менялись;
- это один bounded run, без повторов ради получения благоприятного исхода;
- более длинный диалог не запускался, потому что target continuity уже не была
  подтверждена на первом переходе.

Следующий шаг — evidence synthesis PR #54: сопоставить этот отрицательный
operational result с PR #48, PR #49 и PR #50, не превращая structural churn в
semantic verdict.
