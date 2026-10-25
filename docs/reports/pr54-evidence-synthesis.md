# PR #54 — evidence synthesis and research decision

Этот отчёт сводит результаты PR #39, #48, #49, #50, #51, #52 и #53, не
объединяя разные экспериментальные переменные. Итоговый verdict —
`not_comparable`; semantic identity во всех live-артефактах остаётся
`not_evaluated`.

## Что действительно измерено

| Этап | Что измерялось | Результат |
| --- | --- | --- |
| PR #39 | историческое сохранение target в Full Snapshot | operational observation, без semantic oracle |
| PR #48 | bounded live multi-turn baseline | structural churn без reduction |
| PR #49 | offline A/B question-selection gate | 1 comparable control, 7 non-comparable |
| PR #50 | Full Snapshot против Explicit Binding | protocol effect, не policy effect |
| PR #51 | frozen matched clarification contract | live не запускался |
| PR #52 | deterministic multi-turn offline gate | 18 fixtures, gate passed |
| PR #53 | matched live A/B, 2 cases × 2 conditions | все четыре клетки потеряли target после первого перехода |

Machine-readable summary: [pr54-evidence-synthesis.json](pr54-evidence-synthesis.json).

Новый bounded receipt: [pr53-live-pilot-20261025-corrective-v2.json](pr53-live-pilot-20261025-corrective-v2.json).
Исторический receipt [pr53-live-pilot-20261025.json](pr53-live-pilot-20261025.json)
сохранён без изменений.

В исправленном runner обе пары имеют
`initial_matched_continuation_not_comparable`: вопрос и answer obligation
подтверждены, но target identity потеряна после первого перехода. Это
операционное наблюдение, а не semantic failure.

## Ответы на исследовательские вопросы

1. **Предотвращает ли host-owned binding повторный или неверно направленный
   вопрос?** В offline synthetic gate B действительно блокирует повторный target.
   В live pilot это не проверено: обе ветки остановились раньше, после потери
   target.

2. **Уменьшает ли запрет повтора churn?** Неизвестно. В offline fixture он
   меняет lifecycle и может остановить диалог раньше; live evidence не дошла до
   второго вопроса.

3. **Сохраняет ли модель host-bound target между уточнениями?** В PR #53 — нет
   наблюдаемого сохранения ни для genome identity, ни для intrinsic present.
   Одного прогона недостаточно для общей модели поведения.

4. **Наблюдается ли structural reduction?** В PR #53 — нет; наблюдался
   structural churn. Положительный offline control PR #49 синтетический и не
   доказывает live semantic progress.

5. **Есть ли сопоставимый переход `U → T/F`?** Нет. Semantic adjudication не
   выполнялась, а `semantic_identity` остаётся `not_evaluated`.

6. **Становится ли диалог информативнее?** Установить нельзя. Измеренные
   различия пока механические: binding, stop reason и structural trace.

7. **Что остаётся неидентифицированным?** Semantic meaning ответа, качество
   refinement текста, истинность target continuity и связь structural reduction
   с Onto4 verdict.

## Консервативное решение

Общий результат — `not_comparable`, а не `A_better_observed` и не
`B_better_observed`. Текущие данные не оправдывают production promotion и не
подтверждают преимущество target-aware clarification.

Следующее направление — отдельно исследовать provider target binding: почему
обе protocol-valid refinement ветки теряют host target уже на первом переходе.
Нужно сначала получить сопоставимый successor с сохранённой provenance, а затем
возвращаться к вопросу о повторных уточнениях. Не следует добавлять новые
selection layers только ради повышения operational score.

## Границы evidence

- PR #39 не изменялся;
- PR #49–#53 остаются Draft;
- production admission не менялся;
- prompts, answers, credentials и raw provider payloads не публиковались;
- live pilot не повторялся ради благоприятного исхода.
