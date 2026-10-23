# PR #48 — bounded live multi-turn Bonsai pilot

Этот отчёт фиксирует один ограниченный live-прогон от `main` после merge PR #47. В отличие от deterministic fixtures, ответы на три уточняющих хода были переданы работающему Bonsai endpoint через обычный stdin. Runner сохранил только redacted lifecycle и числовые наблюдения; тексты ответов, prompts и provider payloads в артефакт не записывались.

## Что проверялось

Целью было проверить не семантическую правильность ответа, а сохранение host state между несколькими реальными model-backed ходами:

- были ли приняты три последовательных ответа;
- сохранялась ли assessment и refinement state между ходами;
- менялась ли наблюдаемая структура неопределённости;
- остановился ли loop по host bound `max_turns=3`;
- не создавались ли production admission или semantic-adjudication receipts.

Это operational observation live-модели. Он не является доказательством semantic identity и не заменяет независимую adjudication.

## Параметры запуска

- endpoint: локальный OpenAI-compatible Bonsai endpoint `http://127.0.0.1:8080/v1`;
- model: `Ternary-Bonsai-2-27B-PQ2_0.gguf`;
- host context: `identity_and_genome`;
- `max_turns`: `3`;
- temperature: `0.0`;
- thinking: disabled;
- live run: да;
- semantic identity: `not_evaluated`.

Публичный артефакт: [pr47-live-multiturn-20261024.json](pr47-live-multiturn-20261024.json).

## Наблюдаемый результат

| Измерение | Snapshot 0 | Snapshot 1 | Snapshot 2 | Snapshot 3 |
| --- | ---: | ---: | ---: | ---: |
| `ambiguity_count` | 2 | 2 | 2 | 2 |
| `reading_count` | 2 | 2 | 2 | 2 |
| `presupposition_count` | 3 | 4 | 4 | 4 |
| `assessment_count` | 2 | 2 | 2 | 2 |
| `unknown_verdict_count` | 2 | 2 | 2 | 2 |
| `structural_open_count` | 2 | 2 | 2 | 2 |

Итоговая дельта:

- `structural_reduction_observed`: `false`;
- `epistemic_reduction_observed`: `false`;
- `epistemic_reduction_status`: `not_comparable`;
- `observed_reduction`: `none_observed`;
- `answers_consumed`: `3`;
- `turns`: `3`;
- `stop_reason`: `max_turns_reached`.

Модель трижды вернула уточнение того же общего типа. Между ходами изменилось число presuppositions, но ambiguity и число неизвестных вердиктов не уменьшились. Поэтому этот прогон не показывает устранения исходной неопределённости.

Progress ledger содержит три host-admitted transition entries, но `refinement_committed` остаётся `false`, а structural vector не уменьшается. Это различие важно: наличие перехода snapshot не равно разрешению пользовательского смысла.

## Границы и артефакт

В артефакте подтверждены:

- `provider_payloads_recorded: false`;
- `production_admission_changed: false`;
- `semantic_adjudication_receipt_created: false`;
- `semantic_identity: not_evaluated`.

Публичный JSON содержит только host-owned aliases (`snapshot-N`, `question-N`, `case-0`), безопасные lifecycle events и числовые метрики. Ответы и prompts отсутствуют.

## Вывод

Bounded multi-turn loop на реальном Bonsai endpoint технически прошёл три хода и корректно остановился по host limit. В этом конкретном прогоне модель не уменьшила наблюдаемую structural или epistemic uncertainty: она продолжила возвращать уточнение, не зафиксировав проверяемое разрешение исходной ambiguity.

Следующий эксперимент, если потребуется, должен менять только host fixture или стратегию вопросов и сравнивать такие redacted traces. Нельзя трактовать этот результат как semantic failure или как доказательство неверности исходного пользовательского смысла: semantic adjudication здесь намеренно не выполнялась.
