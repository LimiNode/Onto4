# Отчёт по первому прогону `epistemic-ontology-v1`

Дата прогона: 15 октября 2026 года. Это диагностический отчёт по текущему
model-backed CLI-срезу. Он не меняет семантические контракты и не является
утверждением, что Bonsai уже прошёл corpus.

Отчёт относится к исходной версии корпуса из 26 семантических кейсов. Позднее в
тот же YAML добавлен `genetic-essentialism-dialogue` как protocol fixture. Поэтому
в опубликованном файле сейчас 27 записей: 26 исходных кейсов и один
нетестированный в Bonsai диалоговый fixture.

## Что зафиксировано до запуска

В `apps/onto4-cli/eval/clarification/epistemic-ontology-v1.yaml` записано 27
кейсов. Первые 26 образуют исходный семантический прогон, а
`genetic-essentialism-dialogue` зафиксирован отдельно как protocol fixture.
Кейсы разделены на несколько классов:

- осмысленное утверждение без предоставленного evidence (`U`, а не `F`);
- category/type mismatch (`C`);
- исторические ontology commitments (теплород и флогистон);
- reference и presupposition failure;
- explicit evidence и conflict;
- обычные `T`/`F` control cases;
- два диалоговых сценария, где сначала требуется ontology clarification.

Hidden oracle остаётся вне model-facing input. Это проверяется unit-тестом, а
сам корпус намеренно не добавлен в таблицы обычных kernel-тестов.

Локальная проверка репозитория:

```text
python -m pytest -q
240 passed
python -m compileall -q src tests
success
```

Локальный endpoint Bonsai 2 отвечает на `/v1/models` как через
`127.0.0.1:8080`, так и через `192.168.0.104:8080`.

## Наблюдаемое поведение Bonsai 2

Полный прогон исходных 26 кейсов выполнялся через `onto4 ask` с тем же provider
boundary, который используется CLI. В bounded-параллельном режиме получилось:

```text
15  ProviderTransportError / request timeout
10  внешний timeout процесса
 1  полный ответ
```

Это не 25 semantic failures: четыре одновременных запроса оказались слишком
тяжёлыми для локального 27B endpoint. Поэтому эти строки фиксируют прежде
всего operational limit текущей конфигурации, а не свойства Onto4.

Единственный полный ответ был на control-case:

```text
«2 больше 1.»
→ landscape: FormalizationUnresolved
→ disposition: AskClarification
→ вопрос: «Что именно означает “больше” в этом вопросе?»
```

Ожидался обычный arithmetic `T` без clarification. Это уже содержательная
ошибка model-backed слоя: модель не удержала заранее заданный ordinary
arithmetic reading и не дошла до formalization, хотя запрос был простой.

После снижения параллелизма отдельно проверен category-case:

```text
«Суббота лежит в кровати.»
interpretation: schema_valid (46.3 s)
formalization: schema failure (43.5 s)
error: candidates[0].formalization is missing fields: ['left', 'right']
```

Здесь система пока не получила шанса решить, является ли утверждение `C`.
Формализатор выдал неполную структуру бинарного предиката, и fail-closed
adapter остановил pipeline. Это полезный model-behavior сигнал, а не повод
ослаблять typed AST или автоматически выдавать `C` на основании текста.

Для `2 больше 1` отдельный последовательный запуск ранее дал тот же результат
примерно за 53 секунды. Следовательно, clarification по «больше» не был только
артефактом параллельной нагрузки.

## Моя оценка причин

Сейчас видны три разные проблемы, их нельзя смешивать:

1. **Transport/capacity.** Строгий prompt и две последовательные model-stage
   занимают около 90 секунд на category-case. Таймаут 60 секунд и concurrent
   fan-out не подходят для честного corpus run на этом endpoint. Нужен
   последовательный bounded runner с измерением времени, а не повышение
   семантической терпимости adapter'а.

2. **Interpretation prompt.** Простое «2 больше 1» было переусложнено до
   Meaning clarification. Нужны control-примеры и явная инструкция не создавать
   ambiguity там, где ordinary arithmetic profile уже фиксирует смысл.

3. **Formalization prompt/schema alignment.** Для «Суббота лежит в кровати»
   модель сохранила relation shape, но не заполнила обязательные `left`/`right`.
   Контракт правильно остановил такой ответ. Следующий эксперимент должен
   проверить prompt-примеры и host-side projection аргументных ролей; ослаблять
   обязательные поля нельзя, иначе мы потеряем provenance.

Отдельно остаётся архитектурное ограничение: текущая команда `onto4 ask` делает
только один pass. Диалоговые кейсы `caloric-*` пока можно зафиксировать и
проверить на уровне corpus/fixture, но нельзя честно объявить их пройденными
через интерактивный Bonsai loop.

## Что не следует менять до ревью

- не превращать отсутствие evidence в `F`;
- не превращать schema failure в `C` или `U`;
- не принимать model-generated `T/F/U/C` как authoritative verdict;
- не ослаблять обязательные аргументы typed AST;
- не добавлять автоматический reassessment или persistence ради этого прогона.

Следующий корректive pass должен быть отдельным PR после ревью этого отчёта:
сначала runner/timeout policy и prompt control cases, затем повторный
последовательный прогон. Только после этого имеет смысл решать, нужна ли
архитектурная доработка formalization projection или интерактивного loop.

## Первый interactive pass после corrective changes

После этого отчёта CLI был переведён на host-bound per-reading/context path и
получил bounded interactive loop поверх `ReasoningSession`:

```text
InterpretationSpace
  -> reading × context formalization
  -> clarification question
  -> free-form answer
  -> successor snapshot
  -> explicit reassessment
```

Host проверяет неизменность `source_text` и `conceptual_depth`, связывает
transition IDs и не принимает ответ, который возвращает идентичный snapshot.
Ответ `none_of_the_above` не вызывает модель и сохраняет текущий snapshot без
навязанного выбора.

Unit-проверка после изменений:

```text
После corrective pass локальный набор приложения содержит 267 passed.
compileall — success
git diff --check — чисто
```

## Что объяснило timeout и schema failures

Первоначальный timeout refinement не был свидетельством семантической
сложности ответа. Chat template Bonsai 2 по умолчанию включал скрытое
рассуждение с усилием `xhigh`. При ограничении `max_tokens` вся квота уходила
в `reasoning_content`, а `message.content` оставался пустым; endpoint завершал
ответ с `finish_reason=length`. Поэтому простое увеличение или уменьшение
лимита вывода не решало проблему.

Для structured JSON stages CLI-профиль по умолчанию передаёт transport-параметр
`chat_template_kwargs: {enable_thinking: false}` и температуру `0`. Это
отдельная runtime-политика CLI, а не ослабление схемы; возможность включить
рассуждение сохранена явным флагом. Базовый клиент не навязывает
llama.cpp-расширение endpoint'ам, которые его не поддерживают. Диагностика также фиксирует
`finish_reason` и число completion tokens, не выводя тело ответа модели.

Отдельная prompt-проблема была в per-reading formalizer: модель пыталась
добавлять логические следствия и несколько предикатов вместо одной
формализации выбранного reading. Prompt теперь требует одну завершённую
expression для данного reading и запрещает добавлять другие предикаты или
следствия. Typed AST по-прежнему проверяется строго.

После этих изменений Bonsai 2 в русском сценарии генетического эссенциализма
прошёл initial interpretation, несколько per-reading formalization stages,
первый clarification, свободный ответ, successor snapshot и explicit
reassessment. При ограничении `--max-turns 1` CLI остановился на границе
следующего вопроса без timeout и schema failure. Это подтверждает исправление
runtime/model-boundary проблемы, но ещё не подтверждает содержательную
корректность всех следующих вопросов.

Ранее host останавливал переход, когда refinement возвращал прежний
interpretation snapshot, с ошибкой:

```text
Clarification refinement did not produce semantic successor content.
```

Это ожидаемое fail-closed поведение границы, но не успешное завершение
диалога и не semantic verdict. Следующий эксперимент должен отдельно оценить
содержательность вопросов и successor snapshots, не смешивая её с
transport/runtime ошибками.

## Interactive contract after the corrective pass

В interactive mode список `choices` остаётся подсказкой, а не замкнутым
перечнем допустимых ответов: пользователь может ответить свободным текстом или
ввести `none_of_the_above`. Строгие fixture-вызовы сохраняют прежнюю проверку
перечисленных вариантов.

Переход сначала подготавливается и проходит проверки provenance, непрерывности
истории и semantic progress. Только после этого обновляются
`ClarificationSession` и ledger; отказ на поздней проверке не оставляет
частично записанного перехода.

Интерактивный CLI явно сообщает причину остановки:
`complete`, `need_evidence`, `no_new_admissible_question` или
`max_turns_reached`. Машинный JSON-формат для interactive режима пока явно
запрещён, чтобы prompt-строки не смешивались с JSON на stdout.

## Host-controlled progress admission

После этого прогона в interactive loop добавлен отдельный host-owned ledger
уточнений. Он хранит `question_id`, `target_ids`, ответ и классификацию
перехода:

```text
resolved | structural_resolution | unresolved | new | no_effect | unverified | abstained
```

Один и тот же semantic target больше не выбирается автоматически. Технический
ID может быть переиндексирован host'ом и совпасть с прежним, но новый
semantic target остаётся доступным. Переход,
который отличается от предыдущего snapshot только формально и не затрагивает
целевое различение, отклоняется. Исчезновение target в полном snapshot имеет
статус `structural_resolution`, а не доказанного `resolved`: соответствие
свободного ответа выбранному смыслу ещё требует explicit refinement delta.
При `none_of_the_above` snapshot сохраняется,
но ответ фиксируется как явное воздержание; ложная альтернатива не навязывается.

Система не требует, чтобы число ambiguities всегда уменьшалось: уточнение
может обнаружить новую предпосылку. Требование к прогрессу слабее и точнее —
ответ должен разрешить целевое различение, изменить его статус либо явно
оставить его открытым. Если новой допустимой линии уточнения нет, loop
завершается с явной причиной, а не повторяет тот же вопрос бесконечно.
