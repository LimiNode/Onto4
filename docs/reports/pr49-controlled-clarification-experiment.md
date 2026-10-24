# PR #49 — controlled clarification strategy experiment

Этот research-only increment проверяет источник structural churn, наблюдавшегося в live baseline PR #48. Сравниваются две стратегии на одних и тех же immutable snapshots:

- **A** — текущая `FixtureClarificationPolicy`;
- **B** — минимальная host policy с явной привязкой snapshot-local ambiguity к host-owned semantic target family.

Ни одна стратегия не получает target binding из текста, позиции объекта или похожести терминов. Если B не находит явной привязки, она останавливается fail-closed.

## Offline gate

Запущены шесть paired fixtures:

1. повторная структурная перерегистрация одной host semantic target;
2. изменение structural signature при сохранении target;
3. исчезновение ambiguity;
4. появление новой, не привязанной ambiguity;
5. отсутствие host grounding;
6. отсутствие перехода snapshot.

Обе стратегии получают один и тот же initial snapshot. Ответы заданы как внутренние fixture obligations, связанные с host target; их текст не публикуется.

Публичный redacted artifact: [pr49-offline-ab-20261024.json](pr49-offline-ab-20261024.json).

## Результаты

| Case | B target observation | Structural result | Stop reason | Pair verdict |
| --- | --- | --- | --- | --- |
| `case-0` | target preserved 3 раза, повтор выбранного target 2 раза | churn, reduction нет | `max_turns_reached` | `not_comparable` |
| `case-1` | target preserved при изменении signature | reduction есть | `no_admissible_question` | `not_comparable` |
| `case-2` | target исчезает вместе с ambiguity | reduction есть | `no_admissible_question` | `not_comparable` |
| `case-3` | новая ambiguity не имеет binding | fail-closed | `unbound_target` | `not_comparable` |
| `case-4` | initial target не имеет binding | fail-closed | `unbound_target` | `not_comparable` |
| `case-5` | snapshot не изменился | reduction нет, churn нет | `no_progress` | `not_comparable` |

В условии A все scripted host-target answers получают `question_intent_mismatch`: текущая policy выдаёт структурные target IDs без проверенной semantic binding. Поэтому нельзя подать один и тот же ответ как будто он относится к тому же host target в обеих условиях. Это намеренно оставляет paired verdict `not_comparable`, а не создаёт искусственное преимущество B.

Агрегированный offline verdict: `not_comparable`.

Это не означает, что B лучше или хуже. Offline gate подтверждает механику сравнения: target preservation, повторный выбор, structural churn, structural reduction, fail-closed для unbound target и остановку без прогресса измеряются раздельно.

## Границы

- live Bonsai в этом offline increment не запускался;
- semantic identity: `not_evaluated`;
- epistemic `U → T/F` transitions не оценивались;
- production admission не менялся;
- `SemanticAdjudicationReceipt` не создавался;
- PR #39 не изменялся;
- prompts, answers, provider payloads и target IDs в artifact не публикуются.

Следующий matched live pilot возможен только после содержательного ревью offline gate. Он должен использовать те же source, context, model, temperature, token budget и `max_turns` для A/B и отдельно отмечать `question_intent_mismatch`.
