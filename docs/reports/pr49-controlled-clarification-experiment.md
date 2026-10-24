# PR #49 — controlled clarification strategy experiment

Это research-only offline-эксперимент. Он проверяет, как меняется выбор
уточняющего вопроса, когда host явно связывает snapshot-local ambiguity со
стабильной semantic target. Эксперимент не объявляет semantic identity,
epistemic progress или production admission.

Сравниваются две стратегии:

- **A** — текущая `FixtureClarificationPolicy`;
- **B** — минимальная host-owned policy с явным ledger уже обработанных
  semantic targets.

Обе стратегии работают с одной и той же immutable последовательностью
synthetic snapshots. Ни одна стратегия не получает binding из позиции объекта,
структурного ID, label или текстовой похожести.

## Что изменено в offline gate

Добавлен один comparable positive control. В нём initial snapshot содержит
явный host-issued `target_id`, а политика A получает для этого target такую же
проверенную provenance, как и B. Поэтому обе стратегии могут задать один и тот
же вопрос. Это контроль корректности сравнения, а не доказательство
преимущества какой-либо стратегии.

Для B добавлен минимальный ledger выбранных targets. Он:

- сохраняет target при structural reindex;
- не задаёт вопрос повторно для уже обработанного target без нового основания;
- ищет следующую bound ambiguity после первой unbound ambiguity;
- допускает новый явно связанный target;
- останавливается с `unbound_target`, если grounding отсутствует полностью;
- останавливается с `no_new_admissible_target`, если новые допустимые targets
  закончились.

`no_new_admissible_target`, `unbound_target`, `question_intent_mismatch` и
`no_progress` не считаются semantic resolution.

## Fixtures

Offline gate содержит восемь paired fixtures:

1. повторная структурная перерегистрация одного host target;
2. изменение structural signature при сохранении target;
3. исчезновение ambiguity;
4. появление нового явно связанного target;
5. отсутствие host grounding;
6. отсутствие перехода snapshot;
7. unbound ambiguity перед bound ambiguity;
8. comparable positive control с общей host provenance.

Публичный artifact содержит только aliases, outcomes и числовые метрики:
[pr49-offline-ab-20261024.json](pr49-offline-ab-20261024.json). Prompts,
answers, provider payloads и private target IDs не публикуются.

## Результат

После corrective pass runner воспроизводит:

- `8` paired rows;
- `1` comparable pair — positive control, `no_observed_difference`;
- `7` non-comparable diagnostics;
- `1` fail-closed pair из-за полного отсутствия grounding;
- aggregate verdict: `not_comparable`.

Структурные метрики показывают поведение fixtures, но не semantic progress.
В частности, `target_preservation_count` означает непрерывность заранее
заданной host binding map на synthetic snapshots. Это не наблюдение, что
модель или production host самостоятельно сохранили binding.

В comparable control обе стратегии задают один host-grounded вопрос и затем
наблюдают одинаковое структурное уменьшение ambiguity. Это подтверждает, что
сам механизм сопоставления способен обработать честную positive pair. Для
остальных fixtures сравнение остаётся `not_comparable`, поскольку одна из
стратегий останавливается на mismatch или fail-closed boundary.

## Ограничения

- live Bonsai в этом offline increment не запускался;
- semantic identity: `not_evaluated`;
- epistemic переходы `U → T/F` не оценивались;
- semantic oracle отсутствует;
- structural reduction не повышается до semantic verdict;
- production admission не менялся;
- `SemanticAdjudicationReceipt` не создавался;
- PR #39 не изменялся;
- prompts, answers, provider payloads и target IDs в artifact отсутствуют.

Следующий matched live A/B pilot допустим только после отдельного
содержательного review этого offline gate. Он должен использовать один и тот
же source, context, model, temperature, token budget и `max_turns` для обеих
стратегий, а `question_intent_mismatch`, unsupported и fail-closed исходы
должны оставаться отдельными результатами.
