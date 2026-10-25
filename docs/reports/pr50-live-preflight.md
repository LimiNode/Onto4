# PR #50 — live paired preflight

Это первый ограниченный live preflight для следующего A/B-эксперимента. Он
проверяет не качество семантического ответа, а более узкое условие
сопоставимости: обе стратегии должны получить один и тот же host-issued
вопрос и один и тот же scripted answer от одной исходной точки.

## Условия запуска

- endpoint: локальный llama.cpp OpenAI-compatible `/v1`;
- модель: `Ternary-Bonsai-2-27B-PQ2_0.gguf`;
- temperature: `0`;
- thinking: disabled;
- `max_output_tokens`: `1024`;
- порядок условий: `full_snapshot`, затем `explicit_binding`;
- один host-grounded сценарий, один ход;
- run id: `pr50-bonsai-20261025-preflight-01`;
- source SHA: `e897eaf0ed3450de30cefcfe34b011d7b4936093`.

Артефакт: [pr50-live-preflight-20261025.json](pr50-live-preflight-20261025.json).
В endpoint metadata не было digest модели, поэтому `model_artifact_digest` имеет
значение `null`; это ограничение воспроизводимости явно сохранено в JSON.

## Результат

Обе клетки выполнились со `schema=valid`, `lineage=valid` и
`transition=valid`. Host contract подтверждён: исходная точка, вопрос и ответ
одинаковы для обеих стратегий.

| Условие | Target в successor | Structural admissibility | Semantic identity |
| --- | ---: | ---: | --- |
| `full_snapshot` | нет | false | `not_comparable` |
| `explicit_binding` | да | true | `unverified` |

Итоговый verdict — `not_comparable`. Это не semantic failure и не доказательство
превосходства explicit binding: semantic oracle в preflight отсутствует.
Сравнивался только host-owned binding contract и техническая валидность
successor/provenance.

## Границы результата

- semantic adjudication receipt не создавался;
- production admission не менялся;
- prompts, answer и provider payloads в публичный JSON не записывались;
- `semantic_identity` остаётся `not_evaluated`;
- второй сценарий и трёхходовый paired pilot пока не запускались.

Следующий запуск допустим только после проверки этого preflight. Если он будет
продолжен, нужно сохранить тот же host-issued вопрос и ответ в обеих условиях,
а при любом расхождении оставить пару `not_comparable`.
