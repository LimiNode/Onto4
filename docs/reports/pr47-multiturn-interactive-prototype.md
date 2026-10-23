# PR #47 — bounded multi-turn interactive prototype

Этот research-only прототип продолжает интеграционный smoke из PR #46. В
PR #46 ответ был заранее зафиксирован и разрешался только один ход. Здесь
каждый ответ поступает через обычный пользовательский ввод, а число ходов
остаётся ограниченным host-политикой.

## Что проверяет прототип

Главный вопрос — не сколько вопросов задал интерфейс, а изменилась ли
структура неопределённости после ответа пользователя. Поэтому runner не
сводит результат к одному числу и не называет исчезновение ambiguity доказанной
семантической идентичностью.

Для каждого наблюдения сохраняется redaction-safe вектор:

- число `ambiguity` и `reading`;
- число presuppositions;
- число открытых ontology targets;
- число assessments и unresolved assessments;
- число `U`-вердиктов;
- landscape, disposition и причина остановки.

Модель различает structural uncertainty и неизвестность из-за недостатка
evidence. Поэтому уменьшение `ambiguity_count` не означает автоматически
уменьшение `unknown_verdict_count`, а `U` не превращается в семантическую
ошибку.

## Границы

Runner:

- принимает ответы через `input()` и ограничивает число ходов параметром
  `--max-turns`;
- публикует только число полученных ответов, lifecycle events и векторные
  дельты;
- не публикует текст ответов, provider payloads, credentials или исходные
  prompts;
- не создаёт `SemanticAdjudicationReceipt`;
- не меняет production admission;
- не утверждает историческую semantic identity PR #40.

Полевой Bonsai-прогон в этот increment не включён. Детерминированные тесты
используют два host snapshots и один введённый ответ, чтобы проверить именно
многоходовую механику и расчёт векторной дельты без сетевого вызова.

## Наблюдаемая дельта

`uncertainty_delta` содержит разности `final - initial` для каждого измерения.
`observed_reduction` может иметь значения `structural`, `epistemic`,
`structural_and_epistemic` или `none_observed`. Это operational evidence о
состоянии host snapshots, а не универсальная оценка смысла пользовательского
высказывания.

В deterministic fixture один ответ удаляет одну ambiguity:

| Измерение | До | После | Дельта |
| --- | ---: | ---: | ---: |
| `ambiguity_count` | 1 | 0 | -1 |
| `structural_open_count` | 1 | 0 | -1 |
| `unknown_verdict_count` | 0 | 0 | 0 |
| ответы пользователя | 0 | 1 | +1 |

Результат остаётся `semantic_identity = not_evaluated`.

## Воспроизведение

Детерминированная проверка выполняется без сети:

```text
cd apps/onto4-cli
python -m pytest -q tests/test_pr47_multiturn_interactive_prototype.py
```

Для ручного bounded-прогона с реальным endpoint:

```text
python research/pr47_multiturn_interactive_prototype.py \
  --endpoint http://127.0.0.1:8080/v1 \
  --model Ternary-Bonsai-2-27B-PQ2_0.gguf \
  --context profiles/contexts/identity_and_genome.yaml \
  --max-turns 3 \
  --output ../../docs/reports/pr47-multiturn-interactive-prototype.json
```

Путь к context должен указывать на host-owned fixture из локального окружения;
его содержимое и ответы пользователя в опубликованный отчёт не копируются.
