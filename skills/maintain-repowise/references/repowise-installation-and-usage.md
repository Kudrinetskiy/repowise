# RepoWise: patched-установка и рабочий процесс для локальных проектов

## Проверенный target и состояние пользовательской установки

- Эта публичная инструкция не описывает текущую установку конкретного пользователя. До выбора рецепта определить фактический runtime, индексы и MCP-маршруты; публикация fork не означает установку или миграцию.
- Проверенный опубликованный target — patched `0.55.0@428c62fd10c5069b1c2dba5c68145673bb944338` поверх официального `e829775bfd18f22ff2f9522d514d3b94c1fde2b6`. Pin относится к проверенному runtime-коммиту, а не к последующим documentation-only коммитам `main`; annotated `fork-v0.48.0-patched` сохраняет `35ea9f923de5bb8a3da847284551316c2708190e`.
- Проверки кандидата, сборка и synthetic smoke не являются acceptance живых индексов. Целевая объединённая матрица: `383 passed`; Ruff/format-check: 46 изменённых Python-файлов; diff check и четыре wheel/sdist-пары успешны. Полный `make test-fast`: `27146 passed, 12 failed, 20 skipped, 4 xfailed`; три fork-owned test-fixture failures исправлены (HTTP-модуль `37 passed`, затем общая матрица `383 passed`), все девять остальных failures точно воспроизведены на официальном теге. Полный suite не объявляется GREEN; публикация использует согласованное upstream-failure исключение.
- Обновление глобального tool и первый доступ нового runtime к индексам — отдельные явно разрешённые операции. До первого доступа сохранить индексы/workspace metadata; даже `status` или preview может вызвать schema migration.
- Invocation policy skill остаётся explicit-only: `allow_implicit_invocation: false`. Не менять её вместе с target pin.

### Операционный контракт target 0.55

Шаблоны update/generate/workspace/reindex/init проверены по фактическим опциям собранного patched CLI 0.55; совместимые команды сохраняются для 0.48 runtime. Выбор runtime определяется текущей установкой, не целевой версией этой инструкции. Исторические проверки 0.48 не отменяют следующие 0.55-контракты persistence, unchanged и digest.

Native отчёт сохраняет `written`, `unchanged`, `retired`; checkpoint `completed_page_ids` включает reused/unchanged, а `failed` и `skipped` учитываются отдельно. Не придумывать checkpoint-поля `written_page_ids`. Для вновь written страниц нужна persistence после UTC-границы; для unchanged — точный planned ID, outcome текущего запуска и совпадение сохранённых ранее content/hash. Старый timestamp у такой строки допустим. `12 written + 4 unchanged` может полностью закрыть plan из 16 IDs при доказанном identity и отсутствии failed/skipped/unaccounted; это не «только 12 из 16». Retired IDs отдельно объяснить и сверить, не скрывать исчезновение planned ID.

В 0.55 сохранённый `metadata_json.reused_from_prior_run` позволяет найти точные reused IDs через `json_extract(metadata_json, '$.reused_from_prior_run')`. Сверить их с checkpoint/native report текущего запуска и pre-run content/hash; один marker от прежнего запуска ничего не доказывает.

Contamination audit ниже проверяет `content` и optional `digest` через SQLite `mode=ro` и `PRAGMA table_info`; он совместим с 0.48 без миграции. Чистый content не оправдывает leaked commentary в digest. Сравнение stores в 0.55 основано на eligible SQL search IDs: excluded/below-floor строки намеренно отсутствуют в поиске, raw SQL/vector equality не является acceptance gate и не разрешает reindex.

Dry-run не вызывает модель и не пишет wiki rows/state; это не гарантия неизменности database bytes или всей `.repowise`. Synthetic built-package preview изменял repository metadata/database bytes; update может трогать caches/lock/episodes/WAL/SHM. Schema может мигрировать при первом открытии новой версией. Historical 0.48 filesystem smoke ниже имеет только указанную область доказательства.

Обычный `update`/`--docs` по-прежнему не обновляет существующую concept prose. `generate` запускается для concrete repo, не workspace-wide, без `--no-agents`; provider/model/reasoning брать из согласованного config. Saved Ollama embedder, реальный MCP subprocess smoke в doctor, health rescore и recursive `**` остаются применимыми.

## Публичные примеры и предварительная проверка

Все `/path/to/...` ниже — примеры, а не существующие каталоги. Перед выполнением заменить их подтверждёнными абсолютными путями. `~` означает домашний каталог текущего пользователя. Названия `app`, `app-develop`, `web`, `backend`, `android`, `independent-project` и aliases иллюстративны; не создают обязательную topology.

Примеры ориентированы на macOS, `uv` и Python 3.13. Фактические установку, auth, модель, indexes, workspace и MCP-конфигурацию сначала проверить. Исторический patched 0.48 pin сохранён только для явно разрешённого rollback; целевой runtime — pinned 0.55.

## Содержание

1. Однократная установка RepoWise
2. Проверка Codex CLI
3. Первый индекс основного checkout
4. Локальный Git exclude
5. Подключение RepoWise к Codex
5A. Workspace для нескольких репозиториев
6. Индекс develop worktree
7. Установка в новый самостоятельный проект
8. Обычная работа и выбор LLM-обновления
9. Проверка состояния и поиск
10. Использование через Codex
11. Автоматическое обновление
12. Обновление самого RepoWise
13. Ежедневный чек-лист

## 1. Однократная установка RepoWise

### Подготовленный patched 0.55 — только по отдельной просьбе

До замены CLI отключить затрагиваемые MCP, сохранить `.repowise` всех индексов, которые будут открыты новым runtime, и workspace metadata согласно разделу 12. Команда ниже **не выполнялась** при подготовке fork:

```bash
uv tool install --force --python 3.13 \
  "repowise @ git+https://github.com/Kudrinetskiy/repowise.git@428c62fd10c5069b1c2dba5c68145673bb944338"
repowise --version
uv tool list --show-paths --show-version-specifiers
```

Ожидается `repowise, version 0.55.0`; сам номер не доказывает fork. Проверить `direct_url.json`: `vcs_info.commit_id` должен совпадать с полным pin выше. Не устанавливать официальный PyPI build, текущий изменяемый `main` или локальный `.` вместо него.

Все одиннадцать прежних поведенческих контрактов сохранены. Native 0.55 уже обеспечивает базовый stale loader и обычный zero-symbol refresh; сохранены его digest/migrations и written/unchanged/retired. Перенесены только доказанные gaps: final Codex reply, чистый MCP stdout, existing-only VS Code refresh, restyle persistence/progress, same-run stale decay/failure recovery, Markdown/scoped/near-clone contexts, tombstone FTS, selection/plan parity и additive skipped accounting. Pure near-clone helper вынесен из eager selection initializer для безопасного импорта. Тестовые фикстуры адаптированы к текущим контрактам; старые форматирующие коммиты вслепую не переносились.

Собранный пакет проверен отдельно: фактический CLI, MCP JSON-RPC, четыре preview без вызова модели и записи wiki/state. Synthetic SQLite 0.48 → 0.55 сохраняет prose/model/timestamps/tokens и поддерживает digest/FTS; PostgreSQL и живые индексы этой проверкой не покрыты. Один ранний тестовый HTTP-запрос Ollama вернул 404 без inference; затем fixture заменена in-memory store. Реальные Codex/Ollama generation не запускались.

**Факт автора:** README RepoWise предлагает `pip install repowise`.

Сначала проверить наличие `uv`. Если он отсутствует и пользователь выбрал установку через Homebrew на macOS:

```bash
brew install uv
uv tool update-shell
```

После `uv tool update-shell` открыть новое окно Terminal.

### Историческая pinned-установка 0.48 / rollback

Обычный PyPI-пакет не содержит fork-исправления из этой инструкции. Следующая команда фиксирует исторический patched 0.48 build для отдельно разрешённого rollback, а не новый target. Установка 0.55 приведена в отдельном pinned-блоке выше:

```bash
uv tool install --force --python 3.13 \
  "repowise @ git+https://github.com/Kudrinetskiy/repowise.git@35ea9f923de5bb8a3da847284551316c2708190e"
repowise --version
uv tool list --show-paths --show-version-specifiers
```

Команда Git-установки проверена на опубликованной fork-ветке. Ожидаемая версия:

```text
repowise, version 0.48.0
```

Сам номер версии не отличает fork build от официального `0.48.0`. Надёжные признаки — сохранённая команда установки/вывод `uv` с commit `35ea9f92` и smoke-проверки ниже.

Предварительно удалять официальный или старый fork tool не нужно: `uv tool install --force` атомарно заменяет окружение инструмента с тем же именем. Эта операция не удаляет проектные `.repowise`-индексы; их совместимая миграция выполняется отдельно после обязательного backup. Не запускать эту команду без явной просьбы пользователя.

Локальный clone не нужен для обычной pinned-установки выше. Он нужен только для просмотра, тестирования и развития патчей. Если clone отсутствует, а fork уже создан:

```bash
brew install gh
gh auth login
gh auth status
gh repo clone Kudrinetskiy/repowise \
  /path/to/repowise-fork
cd /path/to/repowise-fork
git remote add upstream git@github.com:repowise-dev/repowise.git
git fetch --all --prune
git switch main
git remote -v
```

Если `upstream` или локальная tracking-ветка уже существуют, повторно их не добавлять; проверить `git remote -v` и `git branch -vv`.

Если fork уже клонирован, для просмотра текущего состояния основной ветки:

```bash
cd /path/to/repowise-fork
git switch main
git pull --ff-only origin main
git rev-parse HEAD
```

Этот блок не устанавливает CLI. Установку выполнять только по проверенному exact published SHA из pinned-команды, а не из произвольного локального состояния или текущего `main`; требуется отдельный запрос пользователя.

### Исторические исправления и проверки fork 0.48

Историческая patched-версия 0.48 содержала одиннадцать рабочих исправлений и один отдельный format-коммит поверх точного `v0.48.0` (`fbb78c4dac8c626f2436fc27f60b891f18850248`):

| Commit | Исправление |
|---|---|
| `657b3ca8` | Codex provider сохраняет только финальное сообщение, а не промежуточные agent-инструкции |
| `40ac0fe5` | MCP stdio не загрязняется обычными логами |
| `18617b82` | `update` не создаёт отсутствующие `.vscode/mcp.json` и `.vscode/extensions.json` |
| `78458b42` | `restyle` показывает прогресс, корректно сохраняет страницы и состояние |
| `d576c609` | обычный update автоматически восстанавливает stale structural file pages без LLM и корректно обрабатывает ошибки persistence |
| `7ec124a5` | Markdown-документация получает полное docs-only source context для структурных file pages и поиска, не отменяя memory-оптимизацию 0.48 для code pages |
| `94609feb` | `doctor` исключает tombstone-страницы из ожидаемого FTS-набора и удаляет их как orphaned, если они остались в FTS; облегчённый запрос загружает `freshness_status` |
| `4eb8545a` | явный structural refresh обновляет stale file pages даже для файлов, из которых parser извлёк ноль symbols |
| `06ab06f1` | форматирует только изменённые локальными патчами Python-файлы |
| `3cc4c681` | явно запрошенные structural file pages восстанавливаются, даже если near-clone дедупликация обычно исключает этот путь |
| `e7384f9e` | planner, scope, cost estimate и generator используют одну near-clone-deduplicated выборку; `--all` исключает retired/obsolete concept IDs |
| `35ea9f92` | JSON checkpoint и CLI явно учитывают runtime skips и сохраняют invariant `planned = completed + failed + skipped` |

Историческая проверка fork 0.48: scope/checkpoint матрица прошла `153 passed`; Ruff, format-check 25 затронутых Python-файлов, `git diff --check` и `uv build --all-packages` успешны. Полный `make test-fast` выполнил `16405 passed`, `13 skipped`, `3 xfailed`; три найденные patch-регрессии были исправлены и повторно закрыты целевой матрицей. Из оставшихся восьми сигналов пять проходят в чистом изолированном окружении, а три идентично воспроизводятся на чистом официальном `v0.48.0` (macOS agent-target baseline, устаревшее ожидание mascot tagline и Git-rebase fixture), поэтому новых fork-only failures 0.48 не осталось. Это не результаты target 0.55; его отдельные результаты указаны в начале инструкции.

Старый отдельный test-isolation patch 0.40 не переносился: его заменило более сильное upstream-решение. Все одиннадцать рабочих исправлений сохранены как отдельные функциональные коммиты; tombstone-патч адаптирован под облегчённый reconciliation-запрос 0.48 и подтверждён RED/GREEN-тестом. Прежний patched `0.47` сохранён в fork annotated-тегом `fork-v0.47.0-patched`.

Фактические пути установки через `uv`:

```text
Команда:     ~/.local/bin/repowise
Окружение:   ~/.local/share/uv/tools/repowise
```

Если после установки команда `repowise` не находится и `uv tool update-shell` ещё не выполнялся:

```bash
uv tool update-shell
```

После этого нужно открыть новое окно Terminal.

### Отключить telemetry

Один раз выполнить:

```bash
repowise telemetry disable
repowise telemetry status
```

Ожидаемый результат:

```text
Telemetry: disabled
reason: disabled via 'repowise telemetry disable'
```

После первого выполнения достаточно периодически проверять состояние командой `repowise telemetry status`.

## 2. Проверка Codex CLI

```bash
codex login status
```

Пример успешного результата при авторизации через ChatGPT:

```text
Logged in using ChatGPT
```

Отдельный `OPENAI_API_KEY` для провайдера `codex_cli` не требуется. Генерация использует текущую авторизацию и лимиты Codex.

### Provider, model и embedder — разные настройки

- **Provider/model** пишет prose-страницы wiki при `init --prose`/`Everything`, `generate` и `restyle`. В patched RepoWise 0.48.0 plain `update` и `update --docs` не переписывают существующие concept pages, хотя docs-enabled pipeline может использовать provider для decision extraction или session mining. `update --full` является single-repo fast-to-full upgrade и не используется как обычный путь обновления уже существующей prose.
- **Embedder** строит векторы semantic search из уже готовых страниц. Он не пишет wiki и не связан с Distill.
- **Distill** только сжимает вывод shell-команд и хранит раскрываемый raw output; semantic search от него не зависит.

Основные provider-варианты из диалога:

| Provider | Авторизация и расходы | Когда выбирать |
|---|---|---|
| `codex_cli` | Текущий `codex login`; без отдельного API key, но расходует токены/лимиты Codex | Текущий локальный выбор |
| `opencode` | Текущая конфигурация OpenCode | Если генерация должна идти через OpenCode |
| `ollama` | Полностью локальная generation-модель, без API key | Если устраивает локальная скорость/качество и модель уже установлена |
| `gemini`, `openai`, `anthropic`, `deepseek`, `kimi`, `openrouter` | Соответствующий API key и тарификация provider | Когда нужен прямой облачный API и контролируемый billing |
| `litellm` | Собственный proxy перед другим provider | Только при уже настроенном LiteLLM endpoint |
| `mock` | Заглушки вместо настоящего prose | Только тесты/диагностика CLI |

В `codex_cli` пункт `Codex CLI default` следует текущей конфигурации CLI. Сообщение `Smaller is fine` означает, что nano/flash/haiku-класс обычно даёт сопоставимые RepoWise docs дешевле; большая модель не гарантирует лучшую wiki. В примерах `gpt-5.6-luna` и `reasoning low` — возможный пользовательский выбор, а не требование RepoWise; доступность модели проверить в текущем CLI.

`Cost: $0.00` при `codex_cli` означает отсутствие рассчитанной прямой API-цены, но не отсутствие работы модели: `Total tokens` в `repowise status` всё равно отражает учтённый объём generation. Эти токены не записываются в текст инструкции; в state хранится только числовая статистика.

## 3. Первый индекс основного checkout

```bash
cd /path/to/app
git rev-parse HEAD
repowise --version
test -e .repowise/state.json && repowise status
test -e .repowise/state.json && repowise doctor
command -v ollama >/dev/null 2>&1 && ollama list || echo 'ollama: unavailable'
git status --short --untracked-files=all -- \
  .repowise .mcp.json .claude .vscode .codex AGENTS.md
```

Если проверка показывает здоровый существующий индекс, `init` не запускать. Если индекса действительно нет, отдельно согласовать политику embedder по 7.3 и предложить пользователю три равноправных варианта из 7.4: интерактивный мастер, явный структурный init или явный model-written init.

`--no-editor-setup` запрещает машинную editor-регистрацию, но сам по себе не отключает проектные `CLAUDE.md`, `AGENTS.md` и `.codex/*`; поэтому текущий шаблон всегда дополняет его `--no-claude-md --no-agents --no-codex --no-distill-hook`.

Таблица ниже показывает **пример** настройки, а не автоматические ответы. Использовать значения только после подтверждения пользователя; в интерактивном диалоге выбирать пункты по названиям, потому что номера могут измениться:

| Вопрос | Выбор |
|---|---|
| How much should repowise write? | `Everything` |
| Customize indexing & generation options? | `n` |
| Provider | `codex_cli` |
| Model | `gpt-5.6-luna` |
| Reasoning effort | `low` |
| Documentation style | `caveman` — выбранный пользователем формат |
| Terminal wants access to control Codex Computer Use | `Don't Allow` |
| Continue after the generation estimate? | Просмотреть оценку и выбрать `y` |
| Install post-commit auto-sync hook? | `n` |

Вопросы о `.claude`, `.codex` и Distill не появляются, потому что ответы уже закреплены явными `--no-*` флагами. Это ожидаемое поведение, а не пропущенный этап.

`Customize indexing & generation options?` открывает commit limit, exclude patterns, concurrency, onboarding, file-page limits и другие advanced-настройки. Ответ `n` не включает `index-only`: он оставляет обычные defaults, а полнота wiki определяется предыдущим выбором `Everything`/`No prose`. Для текущих репозиториев defaults были достаточны; exclusions и concurrency при необходимости можно менять позже в `.repowise/config.yaml` или явными CLI-флагами.

**Факт реализации:** post-commit hook запускает обычный `repowise update`, а репозиторий сохранён в режиме `llm`. Поэтому hook может обращаться к provider после каждого коммита для вспомогательной LLM-работы и расходовать лимиты Codex. Однако в 0.48.0 это не означает автоматическое обновление существующих `module_page`, overview, architecture или onboarding prose.

**Рекомендация:** не устанавливать hook и запускать обновления явно.

Не прерывать `repowise init`, пока команда не вернёт приглашение Terminal.

Если процесс всё же необходимо остановить, готовые страницы сохраняются по мере завершения. Продолжать нужно из того же checkout:

```bash
cd /path/to/app
repowise init --resume
```

Уже записанные страницы не создаются заново; текущая незавершённая страница может быть повторена. Состояние `--resume` принадлежит конкретному checkout и не переносится в `app-develop`.

После завершения:

```bash
repowise status
repowise doctor
```

`repowise status` должен показать созданный индекс и состояние wiki. `repowise doctor` должен завершиться без критических ошибок; необязательные предупреждения не требуют автоматического ремонта.

Базовую установку можно считать корректной, если:

- `repowise --version`, `status` и `doctor` работают;
- `doctor` видит базу, `state.json` и отсутствие stale pages;
- `codex mcp list` показывает `repowise` как `enabled`;
- MCP-инструменты открывают репозиторий из задачи Codex с корнем этого checkout;
- telemetry отключена командой `repowise telemetry disable`.

Только после этой проверки имеет смысл переходить к отдельному индексу worktree.

### Полнотекстовый и семантический поиск

В части уже настроенных локальных индексов осознанно используется `embedder: ollama` и `OLLAMA_EMBEDDING_MODEL=mxbai-embed-large:latest`; это не обязательный default для нового проекта. Если новый индекс показывает `embedder: mock`, структурная база не сломана: граф, Git-анализ, health, wiki и полнотекстовый поиск работают. Ограничение `mock` одно — тестовые векторы вместо полноценного semantic search.

В RepoWise 0.48 явный `init --no-prose` включает неинтерактивный index-only путь и поэтому **не показывает вопрос об embedder**. Наличие модели в `ollama list` само по себе не выбирает её. Если `--embedder` не передан, RepoWise использует сохранённый repo pin при его наличии, затем проверяет `REPOWISE_EMBEDDER`, доступные Gemini/OpenAI/OpenRouter credentials и `OLLAMA_EMBEDDING_MODEL`, а при отсутствии сигнала использует `mock`. Для no-prose пути автоматически найденный hosted embedder по одному API key понижается до `mock`, если пользователь явно не выбрал облачный provider; это защищает от скрытых расходов. После команды всегда проверять фактически сохранённый `embedder:` в `.repowise/config.yaml`.

В установленном Quickstart это описано ниже первых трёх шагов словами: full-text search работает всегда, semantic search требует настроенного embedder, а Ollama является вариантом без ключа. Название автоматического fallback `mock` Quickstart не показывает; оно видно в `repowise reindex --help`, advanced-диалоге и установленном коде выбора provider.

Доступные варианты:

| Вариант | Что даёт | Что требуется | Передача данных |
|---|---|---|---|
| `mock` | Полнотекстовый поиск; тестовые векторы | Ничего | Нет |
| `ollama` | Настоящий semantic search локально | Запущенная Ollama и embedding-модель; default `embeddinggemma` | Нет |
| `gemini` | Облачные embeddings; default `gemini-embedding-001` | `GEMINI_API_KEY` или `GOOGLE_API_KEY` | Текст wiki уходит Gemini |
| `openai` | Облачные embeddings; default `text-embedding-3-small` | `OPENAI_API_KEY` | Текст wiki уходит OpenAI |
| `openrouter` | Облачные embeddings; default `google/gemini-embedding-001` | `OPENROUTER_API_KEY` | Текст wiki уходит OpenRouter |
| auto-detect | Выбирает первый настроенный provider, иначе `mock` | Соответствующая переменная окружения | Зависит от выбранного provider |

Кейсы после базовой установки:

- semantic search пока не нужен — ничего не менять, оставить `mock`;
- нужен локальный semantic search без внешней передачи данных — выбрать Ollama;
- уже используется облачный provider и допустима отправка текста wiki — выбрать Gemini, OpenAI или OpenRouter.

Переход существующего `mock`-индекса на уже установленную локальную Ollama-модель без повторной генерации wiki выполнять как clean reindex с восстановимым backup старой LanceDB:

```bash
cd /path/to/app
mkdir -p .repowise
touch .repowise/.env
chmod 600 .repowise/.env
grep -q '^OLLAMA_EMBEDDING_MODEL=' .repowise/.env 2>/dev/null || \
  printf '%s\n' 'OLLAMA_EMBEDDING_MODEL=mxbai-embed-large:latest' >> .repowise/.env

repowise_vector_backup="/path/to/backups/$(basename "$PWD")-lancedb-$(date '+%Y%m%d-%H%M%S')"
mkdir -p "$(dirname "$repowise_vector_backup")"
test -d .repowise/lancedb
test ! -e "$repowise_vector_backup"
mv .repowise/lancedb "$repowise_vector_backup"

repowise reindex . --embedder ollama
repowise doctor
```

`reindex` заново вычисляет embeddings существующих SQL-страниц, не вызывает модель для написания wiki и после успешной записи сохраняет `embedder: ollama` в `.repowise/config.yaml`. Backup не удалять, пока `doctor` не покажет согласованные SQL/vector/FTS и `Drift=0.0%`. Если в `.repowise/.env` уже указана другая `OLLAMA_EMBEDDING_MODEL`, сначала остановиться и выбрать нужную модель, а не добавлять вторую строку.

### Важно про интеграцию Claude Code

Если запускать просто `repowise init`, ответ `n` на `Generate .claude/CLAUDE.md?` отключает только проектный файл инструкций. RepoWise 0.48.0 при этом может отдельно зарегистрировать глобальные Claude Code MCP и hooks `PostToolUse`/`SessionStart` в `~/.claude/settings.json`, а также создать VS Code integration files.

Отдельный вопрос `Install the Claude Code rewrite hook?` относится к автоматической замене команд на `repowise distill ...`; для Codex MCP выбирать `n`.

Если пользователь выбрал Codex-only конфигурацию без записи editor/project integration, использовать весь набор `--no-editor-setup --no-claude-md --no-agents --no-codex --no-distill-hook`. Если Claude/VS Code-настройки уже созданы, повторный `init` с флагами их не отменяет: удалять их следует отдельно только после проверки существующих файлов и глобального `settings.json`.

## 4. Не добавлять локальный индекс в Git

`.repowise/` — локальная база, кэши и сгенерированный индекс. Корневой `.mcp.json` тоже локальный: сейчас он содержит абсолютный путь этого компьютера. Оба объекта не нужно коммитить.

Чтобы игнорировать каталог только локально и не менять общий `.gitignore`, один раз выполнить в основном checkout:

```bash
cd /path/to/app
repo_exclude="$(git rev-parse --git-path info/exclude)"
grep -qxF '.repowise/' "$repo_exclude" || printf '%s\n' '.repowise/' >> "$repo_exclude"
grep -qxF '.mcp.json' "$repo_exclude" || printf '%s\n' '.mcp.json' >> "$repo_exclude"
```

Этот exclude общий для linked worktree `app-develop`.

Проверка:

```bash
cd /path/to/app
git check-ignore -v .repowise .mcp.json
git status --short --untracked-files=all -- .repowise .mcp.json
```

`git check-ignore -v` должен показать правила из `info/exclude`; `git status` должен быть пустым.

Проверка должна подтвердить, что `.repowise/` игнорируется правилом `.git/info/exclude` и не попадёт в Git.

## 5. Глобально подключить RepoWise к Codex

Сначала определить фактический режим, а не регистрировать MCP вслепую:

- проверить `repowise status` и полный `repowise doctor` в каждом репозитории, который пользователь действительно включил в область задачи;
- сравнить `Last sync commit` с `git rev-parse HEAD`;
- выполнить `codex mcp list` и проверить путь уже зарегистрированной команды;
- проверить только точный `.repowise-workspace.yaml`, который назван пользователем, указан текущей MCP-командой или уже установлен в этой задаче;
- не считать несколько папок, прикреплённых к одному проекту ChatGPT/Codex, признаком RepoWise workspace.

Если нужен ровно один текущий репозиторий и workspace не настроен, после успешного `repowise init` выполнить один раз:

```bash
codex mcp add repowise -- repowise mcp
codex mcp list
```

В списке должна появиться строка `repowise` со статусом `enabled`.

После добавления MCP полностью перезапустить Codex. Project-local `.codex/config.toml` для этого не требуется.

Перезапуск может добавить инструменты RepoWise и в уже открытую задачу, но рабочий каталог задачи при этом не меняется.

Чтобы использовать созданный индекс, нужно открыть задачу Codex с корнем:

```text
/path/to/app
```

Если старая задача уже открыта с правильным корнем `app`, после перезапуска создавать новую только ради загрузки MCP не требуется. Если её корень другой, открыть новую задачу с корнем `app`.

В этом single-repo режиме MCP-сервер запускается из корня текущей задачи Codex. Поэтому:

- задача, открытая в `/path/to/app`, использует индекс этого checkout;
- задача, открытая в `/path/to/app-develop`, использует отдельный индекс worktree.

Если один MCP должен обслуживать несколько отдельных индексов, не полагаться на cwd задачи и не повторять single-repo регистрацию: настроить стандартный RepoWise workspace по разделу 5A и зарегистрировать фиксированный `<WORKSPACE_ROOT>`.

Не нужно вручную оставлять запущенной команду `repowise mcp .`: Codex сам запускает зарегистрированный MCP-сервер.

### Из какой директории запускать команды

- `repowise init`, `status`, `doctor`, `update`, `generate`, `search` и `hook` — из корня конкретного checkout/worktree;
- `codex mcp add repowise -- repowise mcp` и `codex mcp list` — из любой директории, потому что регистрация глобальная;
- Pinned fork install из раздела 1 (только по отдельной просьбе) и `repowise telemetry disable/status` — из любой директории; обычный `uv tool upgrade repowise` не является рецептом обновления нашего fork.

## 5A. RepoWise workspace для нескольких существующих индексов

RepoWise workspace — стандартная возможность RepoWise 0.48. Она объединяет несколько уже индексированных Git-репозиториев под одним MCP-сервером и позволяет обращаться к ним по aliases. Она работает независимо от того, какие папки подключены к проекту ChatGPT/Codex: вложения ChatGPT не создают workspace, не добавляют repos и не переключают RepoWise автоматически.

### 5A.1. Сначала определить текущее состояние

Для каждого репозитория, который пользователь хочет включить, сначала выполнить read-only проверку из раздела 7.1 и дополнительно:

```bash
git -C /абсолютный/путь/к/repo rev-parse --show-toplevel
git -C /абсолютный/путь/к/repo rev-parse HEAD
cd /абсолютный/путь/к/repo
repowise status
repowise doctor
grep -n '^embedder:' .repowise/config.yaml
```

Затем проверить текущее подключение и только заранее известный кандидат workspace root:

```bash
codex mcp list
test -e <WORKSPACE_ROOT>/.repowise-workspace.yaml && \
  sed -n '1,240p' <WORKSPACE_ROOT>/.repowise-workspace.yaml || \
  echo 'workspace config: absent'
test -e <WORKSPACE_ROOT>/.repowise/.env && \
  sed -E 's/=.*/=<redacted>/' <WORKSPACE_ROOT>/.repowise/.env || \
  echo 'workspace env: absent'
```

Не искать workspace произвольным обходом диска и не выводить значения секретов. Если здорового индекса ещё нет, сначала согласовать и выполнить обычный `init` для этого конкретного repo; если индекс здоров, повторный `init` запрещён.

### 5A.2. Выбрать режим по фактам

| Состояние и цель | Правильный маршрут |
|---|---|
| Один repo, workspace config отсутствует | Single-repo команды с `--no-workspace`. |
| Workspace существует, обновить все зарегистрированные repos | `update <WORKSPACE_ROOT> --workspace`. |
| Workspace существует, обновить один repo | `update <WORKSPACE_ROOT> --repo <ALIAS>`. |
| Несколько здоровых индексов, workspace ещё нет | После утверждения root/aliases создать workspace и зарегистрировать индексы без повторного `init`. |
| Нужно переписать concept prose | Выполнить `generate` в конкретном repo; общего workspace-wide `generate` в RepoWise 0.48 нет. |

`--no-workspace` означает сознательно принудительный single-repo режим. Его нельзя добавлять по шаблону до этой проверки.

### 5A.3. Зарегистрировать готовые индексы

Пользователь сначала утверждает точный `<WORKSPACE_ROOT>`, aliases, default repo и общую runtime-конфигурацию. Для repos в разных каталогах и на разных томах удобно выбрать нейтральный каталог, но RepoWise этого не требует. В `<WORKSPACE_ROOT>/.repowise-workspace.yaml` используется стандартная схема 0.48. Во время поэтапной миграции конфигурации должны содержать только индексы, открываемые одной версией runtime.

Пример topology: один workspace обслуживает основной checkout и связанные repositories; второй может обслуживать worktree и те же связанные repositories. Default alias и подключение source-checkout определяет пользователь; не переносить состав чужой установки вслепую.

Для регистрации уже готовых compatible indexes использована такая форма:

```bash
cd <WORKSPACE_ROOT>
repowise workspace add /path/to/web --alias web --no-index
repowise workspace add /path/to/backend --alias backend --no-index
repowise workspace add /path/to/android --alias android --no-index
REPOWISE_SKIP_EDITOR_SETUP=1 repowise update . \
  --workspace --no-agents --index-only
```

Повторный `init`, `generate` или `reindex` при таком подключении не требуется.

Абсолютные paths штатно поддерживаются. Уже здоровые индексы не переинициализировать. Если workspace config уже существует, один готовый repo можно добавить без индексации:

```bash
cd <WORKSPACE_ROOT>
repowise workspace add /абсолютный/путь/к/repo \
  --alias <ALIAS> \
  --no-index
```

Не запускать `workspace add` с default-параметрами для готового индекса: по умолчанию команда запускает индексирование и может включить docs generation.

### 5A.4. Согласовать runtime environment

Workspace MCP загружает `<WORKSPACE_ROOT>/.repowise/.env`, а не `.repowise/.env` каждого дочернего repo. Поэтому до переключения MCP проверить совместимость embedder и embedding model всех индексов.

- `codex_cli` не требует API key;
- для Ollama workspace root должен получить утверждённый `OLLAMA_EMBEDDING_MODEL`, которым построены эти индексы;
- разные embedding models нельзя молча смешивать в одном MCP-процессе;
- смена embedder/model требует отдельного clean reindex по Recipe 11 skill;
- hosted-provider secrets не копировать без отдельного разрешения и никогда не печатать.

### 5A.5. Проверить и подключить MCP

До изменения глобальной регистрации:

```bash
repowise workspace list <WORKSPACE_ROOT>
repowise doctor <WORKSPACE_ROOT> --workspace
```

После явного разрешения заменить единственную глобальную RepoWise-запись:

```bash
codex mcp remove repowise
codex mcp add repowise -- repowise mcp <WORKSPACE_ROOT>
codex mcp list
```

Полностью перезапустить ChatGPT/Codex. MCP `list_repos` должен показать workspace mode, точный root, default alias и все aliases. Затем выполнить по одному read-only RepoWise-запросу для каждого alias.

### 5A.6. Обновлять workspace

Все stale repos в workspace:

```bash
repowise update <WORKSPACE_ROOT> \
  --workspace \
  --no-agents
```

То же гарантированно без provider-dependent работы:

```bash
repowise update <WORKSPACE_ROOT> \
  --workspace \
  --no-agents \
  --index-only
```

Один alias:

```bash
repowise update <WORKSPACE_ROOT> \
  --repo <ALIAS> \
  --no-agents
```

При необходимости добавить `--index-only`. После реального update:

```bash
repowise workspace list <WORKSPACE_ROOT>
repowise doctor <WORKSPACE_ROOT> --workspace
repowise workspace diagnostics <WORKSPACE_ROOT>
```

Требовать совпадения sync commit с фактическим HEAD каждого repo, `0 stale`, `0.0%` drift и полностью успешного `doctor`. `workspace diagnostics` объясняет cross-repo links, но не заменяет health-проверки.

## 6. Создать индекс для develop worktree

Этот раздел выполнять только после того, как базовая установка из разделов 1–5 полностью проверена. Отсутствие индекса в `app-develop` до этого момента не является ошибкой установки.

**Факт автора:** RepoWise умеет быстро создавать индекс worktree из базового checkout, когда последний проиндексированный commit базы является предком HEAD worktree.

**Локальный факт:** сейчас основной каталог находится на `event-history`; `event-history` и `develop` разошлись, и ни одна из них не является предком другой. Поэтому автоматическое быстрое seed-копирование, вероятнее всего, невозможно.

Для `app-develop` сначала выполнить inspection из 7.1 и проверить, существует ли совместимый собственный индекс либо допустимая seed-база. Историческое расхождение веток не считать текущим фактом без проверки ancestry.

```bash
cd /path/to/app-develop
git rev-parse HEAD
test -e .repowise/state.json && repowise status
test -e .repowise/state.json && repowise doctor
git status --short --untracked-files=all -- \
  .repowise .mcp.json .claude .vscode .codex AGENTS.md
```

Если полноценного индекса нет и seed использовать нельзя, согласовать embedder по 7.3, сообщить результаты проверки и предложить пользователю варианты 7.4. Во всех выбранных командах оставить `--no-seed`; не подменять выбор пользователя предположением о требуемой полноте wiki или semantic search. Если seed доказан совместимым, убрать только `--no-seed` из выбранной команды.

Остальные ответы для полного варианта: `codex_cli` → `gpt-5.6-luna` → `low` → `caveman`; project-local Claude/Codex файлы не генерировать; post-commit и Distill hooks не устанавливать.

Для будущего worktree, чей HEAD действительно является потомком проиндексированного commit базы, `--no-seed` не нужен: использовать тот же шаблон без `--no-seed`, и RepoWise попробует seed автоматически.

Если сначала был выбран `No prose`, а затем потребовалась model-written wiki, использовать `generate --unwritten --cascade none` из раздела 7.4. Он переиспользует уже построенные graph/Git данные и заполняет только template/unwritten concept pages с безопасным dry-run плана.

**Patched 0.48 и подготовленный 0.55:** `repowise update --full --dry-run` разрешён как логический preview без модельной генерации и записи wiki/state. Исторический 0.48 smoke имел 26 неизменных файлов; это не универсальная гарантия filesystem immutability. В built 0.55 возможны repository metadata, caches и WAL/SHM. Команда показывает single-repo fast-to-full план; после одобрения тот же `update --full` без `--dry-run` является реальной мутацией индекса. До первого доступа новым runtime нужен backup.

`update --full` использовать только для upgrade одного существующего быстрого/неполного индекса: повторного чтения всего repository, backfill полного Git tier и создания отсутствующих page families. Это не workspace-wide команда и не универсальная перегенерация уже написанной concept prose. Для существующих model-written страниц по-прежнему выбирать `generate --path`, `--page` или `--all`.

`init --dry-run` не является полностью filesystem-read-only: wiki/database и editor setup не сохраняются, но ingestion создаёт recoverable parse/centrality/duplication caches и episode/session DB внутри `.repowise`. Это допустимо только после preflight; не утверждать, что команда не создала ни одного файла.

`update --docs` только переопределяет сохранённый `No prose` режим для одного incremental pipeline, но в RepoWise 0.48.0 по-прежнему работает с `file_pages_only=True` и не обновляет существующую концептуальную AI-wiki. Для model-written concept pages использовать `generate --all`, `generate --path` или `generate --page`.

Проверить второй индекс:

```bash
repowise status
repowise doctor
```

Health, dead-code и hotspot результаты являются аналитическими сигналами, а не доказательствами ошибки или безопасного удаления. Перед изменениями их нужно подтверждать кодом и тестами.

В RepoWise 0.48 изменение health-конфигурации или её fingerprint автоматически запускает полный health rescore на следующем `update`; отдельный `doctor --repair` для этого не нужен. В `health-rules.json` glob `path/*` покрывает только один уровень. Для всего рекурсивного поддерева использовать `path/**`, а затем проверить в preview/output, какие файлы действительно попали под правило.

Нормальный результат `doctor`:

- CLI, Git repository, `.repowise/`, database и `state.json` — `OK`;
- stale pages отсутствуют;
- SQL и vector index не расходятся;
- при зарегистрированном MCP строка `MCP server responds` — `OK`: doctor запускает реальный subprocess и проверяет JSON-RPC handshake;
- post-commit и Distill rewrite hooks не установлены;
- вход в hosted-аккаунт RepoWise необязателен.

## 7. Установка в новый самостоятельный проект

Пример ниже подходит для `/path/to/independent-project` и следующих независимых репозиториев. Глобально устанавливать CLI и регистрировать Codex MCP второй раз не нужно.

### 7.1. Сначала проверить существующее состояние

Агент не должен сразу выдавать полный installation-рецепт. Сначала он сам выполняет безопасную read-only проверку и сообщает пользователю, что уже установлено и настроено:

```bash
cd /путь/к/новому/проекту
pwd
git branch --show-current
git rev-parse HEAD
repowise --version
repowise telemetry status
command -v ollama >/dev/null 2>&1 && ollama list || echo 'ollama: unavailable'
codex mcp list
printf 'REPOWISE_EMBEDDER=%s\n' "${REPOWISE_EMBEDDER:-<unset>}"
for name in GEMINI_API_KEY GOOGLE_API_KEY OPENAI_API_KEY OPENROUTER_API_KEY OLLAMA_EMBEDDING_MODEL; do
  printenv "$name" >/dev/null 2>&1 && printf '%s=set\n' "$name" || printf '%s=unset\n' "$name"
done
test -e .repowise/state.json && echo 'state: present' || echo 'state: absent'
test -e .repowise/config.yaml && echo 'config: present' || echo 'config: absent'
test -e .repowise/.env && echo 'env: present' || echo 'env: absent'
test -d .repowise/lancedb && echo 'vectors: present' || echo 'vectors: absent'
git status --short --untracked-files=all -- \
  .repowise .mcp.json .claude .vscode .codex AGENTS.md
```

Если `.repowise/.env` уже есть, проверять только выбранный embedder/model и имена переменных API keys, не выводя значения секретов. Перед предложением установки агент сообщает, какой embedder RepoWise, вероятно, определит автоматически.

Дальнейшее действие определяется фактами:

| Обнаружено | Что делать |
|---|---|
| Есть `state.json`, база и config | Выполнить `repowise status` и полный `repowise doctor`. При здоровом индексе новый `init` запрещён: выбрать update/generate по реальному sync state. |
| Есть `.repowise/`, но полного state нет | Изучить содержимое, checkpoint/resume evidence и размеры файлов. Не удалять: это может быть пустой MCP scaffold, частичный `init` или неизвестный пользовательский артефакт. |
| После обновления CLI существующий индекс выдаёт schema/migration error | Сохранить backup и диагностировать совместимость; не маскировать проблему свежим `init`. |
| Индекса действительно нет | Сообщить подтверждённое отсутствие и только затем предложить пользователю выбрать способ установки из 7.4. |

Если полноценный state обнаружен, проверить его read-only:

```bash
repowise status
repowise doctor
```

Полноценный индекс подтверждают согласованные `.repowise/state.json`, непустая база со страницами и успешный `doctor`, а не одно имя каталога. Зафиксировать, существовали ли `.claude/`, `.vscode/`, `.codex/`, `.mcp.json` и `AGENTS.md` до RepoWise: postcheck должен отличать прежние пользовательские файлы от созданных установкой. Не просить пользователя выполнять проверки, доступные агенту; не запускать `doctor --repair`, не удалять `.repowise`, не менять editor/MCP registration и не устанавливать/обновлять CLI без соответствующего запроса или разрешения.

### 7.2. Настроить локальный Git exclude

Выполнять только после inspection, когда отсутствие полноценного индекса подтверждено и пользователь решил продолжить установку. До `init` исключить локальную базу и абсолютный MCP-путь из commit:

```bash
repo_exclude="$(git rev-parse --git-path info/exclude)"
mkdir -p "$(dirname "$repo_exclude")"
touch "$repo_exclude"
grep -qxF '.repowise/' "$repo_exclude" || printf '%s\n' '.repowise/' >> "$repo_exclude"
grep -qxF '.mcp.json' "$repo_exclude" || printf '%s\n' '.mcp.json' >> "$repo_exclude"
git check-ignore -v .repowise .mcp.json
```

Для linked worktree правила `git rev-parse --git-path info/exclude` относятся к общему Git repository; отдельную копию правила обычно добавлять не требуется.

### 7.3. Выбрать embedder до `init`

Способ установки и embedder — два независимых решения. Агент не навязывает Ollama и не задаёт вопрос повторно, если пользователь уже выбрал. После inspection предложить один из вариантов:

| Политика | Как передать | Что получится |
|---|---|---|
| Автоопределение | Не передавать `--embedder` | RepoWise применит порядок auto-detect, описанный выше; при отсутствии подходящего сигнала будет `mock`. |
| Выбор в мастере | Не передавать `--embedder`; в интерактивном мастере выбрать `Advanced` или включить customization | Пользователь увидит отдельный вопрос об embedder. Обычный короткий путь мастера может его не показать. |
| Явно закрепить provider | Передать `--embedder <EMBEDDER>` | Воспроизводимый выбор `ollama`, `gemini`, `openai`, `openrouter`, `mock` или другого поддерживаемого значения. |
| Осознанно оставить `mock` | Передать `--embedder mock` | Полнотекстовый поиск без полноценного semantic similarity и без расходов на embeddings. |

Никакой «стандартный настоящий embedder» автоматически не устанавливается. Fallback — `mock`. Если пользователь явно выбрал Ollama, но не закрепил модель, RepoWise 0.48 использует default Ollama-provider `embeddinggemma`. Если repo уже сохраняет `embedder: ollama`, команды с auto-resolution должны сохранить этот выбор; после команды всё равно проверить фактический pin. Если пользователь выбрал конкретно `mxbai-embed-large:latest`, только тогда подготовить модель и `.repowise/.env`:

```bash
ollama list
ollama list | grep -q '^mxbai-embed-large:latest[[:space:]]' || \
  ollama pull mxbai-embed-large:latest
mkdir -p .repowise
touch .repowise/.env
chmod 600 .repowise/.env
grep -q '^OLLAMA_EMBEDDING_MODEL=' .repowise/.env || \
  printf '%s\n' 'OLLAMA_EMBEDDING_MODEL=mxbai-embed-large:latest' >> .repowise/.env
```

Если строка `OLLAMA_EMBEDDING_MODEL` уже существует, сначала проверить её значение и при необходимости заменить вручную; не добавлять вторую строку. Ollama должна быть запущена во время `init`, `reindex` и semantic search. Для auto-detect, выбора в мастере, hosted provider или `mock` этот Ollama-блок не выполнять.

### 7.4. Посмотреть план и выполнить `init`

Сначала пользователь выбирает способ управления установкой и желаемую полноту wiki, затем отдельно политику embedder из 7.3. Агент не выбирает варианты по умолчанию и не спрашивает повторно уже явно указанные решения:

| Вариант | Когда выбирать | Результат |
|---|---|---|
| Интерактивный мастер | Пользователь хочет пройти вопросы RepoWise и самостоятельно выбрать `Everything`, `No prose` или `Advanced`. | RepoWise спрашивает mode/provider/model/style; безопасные editor/hook-ограничения уже заданы флагами. |
| Явный структурный init | Нужна воспроизводимая установка без вопросов и без documentation LLM. | Структурная wiki; full-text или semantic search определяется отдельным выбором embedder. Prose можно добавить позднее. |
| Явный model-written init | Нужна воспроизводимая полная wiki с заранее выбранными provider/model/style. | Dry-run плана и стоимости, затем реальный LLM-init после одобрения; embedder по-прежнему выбирается отдельно. |

Перед командой определить аргументы ровно одним способом; не копировать все строки сразу и не оставлять placeholder:

```bash
REPOWISE_EMBEDDER_ARGS=()                         # auto-detect или выбор в мастере
REPOWISE_EMBEDDER_ARGS=(--embedder ollama)        # пример явного Ollama
REPOWISE_EMBEDDER_ARGS=(--embedder mock)          # осознанно только full-text
```

Для другого явного provider заменить `ollama` на уже выбранное точное значение.

#### Интерактивный мастер

```bash
repowise init . \
  --no-workspace \
  --no-seed \
  "${REPOWISE_EMBEDDER_ARGS[@]}" \
  --no-claude-md \
  --no-agents \
  --no-codex \
  --no-distill-hook \
  --no-editor-setup
```

Агент объясняет текущий вопрос, но не выбирает за пользователя `Everything` / `No prose` / `Advanced`, provider, model, reasoning, style или embedder. Если пользователь выбрал embedder в мастере, нужно войти в `Advanced`/customization; короткий wizard может закончиться без этого вопроса.

#### Явный структурный init

В RepoWise 0.48 явный `--no-prose` отключает интерактивный мастер, поэтому каждый нужный выбор передаётся флагом:

```bash
repowise init . \
  --no-workspace \
  --no-seed \
  --no-prose \
  "${REPOWISE_EMBEDDER_ARGS[@]}" \
  --no-claude-md \
  --no-agents \
  --no-codex \
  --no-distill-hook \
  --no-editor-setup \
  --dry-run

repowise init . \
  --no-workspace \
  --no-seed \
  --no-prose \
  "${REPOWISE_EMBEDDER_ARGS[@]}" \
  --no-claude-md \
  --no-agents \
  --no-codex \
  --no-distill-hook \
  --no-editor-setup
```

`--dry-run` показывает объём и план страниц и не сохраняет wiki/database или editor setup, но RepoWise 0.48 может создать recoverable parse/centrality/duplication caches и episode/session DB внутри `.repowise`. Вторую команду всё равно нужно выполнить. Этот вариант не спрашивает provider/model/style, потому что prose пока не генерируется; это ожидаемо.

#### Явный model-written init

Сначала выполнить dry-run с заранее согласованными значениями:

```bash
repowise init . \
  --no-workspace \
  --no-seed \
  --prose \
  --provider codex_cli \
  --model codex_cli/gpt-5.6-luna \
  --reasoning low \
  --wiki-style caveman \
  --concurrency 10 \
  "${REPOWISE_EMBEDDER_ARGS[@]}" \
  --no-claude-md \
  --no-agents \
  --no-codex \
  --no-distill-hook \
  --no-editor-setup \
  --dry-run
```

После проверки плана и явного одобрения повторить ту же команду, заменив `--dry-run` на `--yes`. Если пользователь выбрал другие provider/model/reasoning/style, подставить именно их; значения выше описывают текущую локальную конфигурацию, а не обязательный default RepoWise.

После завершения:

```bash
repowise status
repowise doctor
grep -n '^embedder:' .repowise/config.yaml
git status --short --untracked-files=all -- \
  .repowise .mcp.json .claude .vscode .codex AGENTS.md
```

При полном наборе `--no-*` новый проект не должен получить `.claude/`, `.vscode/`, `.codex/` или изменение `AGENTS.md`. Если такие файлы появились, не коммитить их автоматически: сначала проверить, не существовали ли они до RepoWise. Patched `update` не создаёт отсутствующие VS Code-файлы повторно.

Если staged-индекс позже нужно дополнить полной model-written wiki, повторный `init` и `update --full` не нужны. Сначала посмотреть точный LLM-план:

```bash
repowise generate . \
  --unwritten \
  --cascade none \
  --provider codex_cli \
  --model codex_cli/gpt-5.6-luna \
  --reasoning low \
  --concurrency 10 \
  --dry-run
```

После проверки количества и типов страниц повторить ту же команду без `--dry-run`. `--unwritten --cascade none` не переписывает уже актуальную model-written prose и избегает ложного dependent-плана; `generate --all` нужен позже только для осознанного полного refresh уже написанной концептуальной wiki. Затем выполнить обязательные checkpoint/persistence/contamination проверки из раздела 8, `repowise status` и полный `repowise doctor`. Если структурной wiki достаточно, этот LLM-этап можно не выполнять вовсе.

## 8. Обычная работа после изменения кода

Сначала повторить короткую state/mode-проверку из 5A.1: текущий HEAD, `status`, полный `doctor`, текущая MCP-команда и известный workspace config. Затем выбрать один маршрут:

- single-repo — команды ниже из конкретного checkout/worktree с `--no-workspace`;
- все repos существующего workspace — команды 5A.6 с `--workspace`;
- один repo существующего workspace — команды 5A.6 с `--repo <ALIAS>`;
- concept prose — `generate` из конкретного repository path, даже если repo зарегистрирован в workspace.

Папки, прикреплённые к проекту ChatGPT/Codex, в этом выборе не участвуют. Блоки с `--no-workspace` ниже являются именно single-repo рецептами.

### Обычное обновление в сохранённом режиме

После обычных коммитов, переключения на ветку-продолжение или перед важным вопросом к Codex:

```bash
cd /путь/к/нужному/checkout
REPOWISE_UPDATE_STARTED_AT="$(date -u '+%Y-%m-%d %H:%M:%S')"
repowise update . \
  --no-workspace \
  --no-agents

sqlite3 -header -column .repowise/wiki.db "
SELECT page_type, COUNT(*) AS persisted, MAX(updated_at) AS newest
FROM wiki_pages
WHERE updated_at >= '$REPOWISE_UPDATE_STARTED_AT'
GROUP BY page_type
ORDER BY page_type;
"
```

Команда выполняет штатную синхронизацию графа, Git-истории, health, индекса, `symbol_spotlight` и `file_page`. В patched RepoWise 0.48.0 даже LLM-backed индекс запускает generation с `file_pages_only=True`: существующие `module_page`, `repo_overview`, `architecture_diagram` и `onboarding` не перегенерируются.

Название `docs-enabled incremental path` не означает обновление концептуальной LLM-прозы. Ветка может использовать настроенный provider для decision extraction или session mining, поэтому plain `update` не гарантирует отсутствие LLM-вызовов. Для гарантированно структурного прогона нужен `--index-only`; для concept prose — отдельный `generate`.

Строки `Generating pages`, `Pages updated`, generation-job totals, накопительный `Total tokens` и `$0.00` не доказывают, что GPT Luna переписала concept pages: эти счётчики включают структурный renderer и другую работу pipeline.

SQL-результат после обычного update классифицировать по `page_type`. `file_page`, `symbol_spotlight`, `infra_page`, `layer_page` и `scc_page` относятся к структурному слою. В 0.48.0 отсутствие новых `module_page`, `repo_overview`, `architecture_diagram` и `onboarding` ожидаемо; не объявлять LLM-прозу обновлённой.

### Гарантированное обновление без модели

Если в этом прогоне нужны только кодовый индекс, граф, Git-данные, health и детерминированные страницы:

```bash
repowise update . \
  --no-workspace \
  --no-agents \
  --index-only
```

Использовать этот вариант также перед отдельным `generate --path`: тогда `update` отвечает за структурный слой, а `generate` — за выбранный LLM-текст, без дублирующих модельных вызовов.

### Upgrade одного быстрого индекса до полного

Если существующий single-repo индекс был создан в fast/reduced режиме и теперь нужны полное повторное чтение repository, полный Git tier и отсутствующие page families, сначала выполнить безопасный preview:

```bash
repowise update . \
  --no-workspace \
  --no-agents \
  --full \
  --dry-run
```

После проверки плана, provider/model и стоимости повторить без `--dry-run`. Это single-repo fast-to-full upgrade, а не workspace-wide команда и не перегенерация уже существующей concept prose. Для смыслового обновления model-written страниц после него отдельно использовать `generate --path`, `--page` или `--all` по критериям следующего раздела.

### Как определить, устарело ли LLM-описание

Контрольный вопрос: **может ли агент, прочитав старую model-written страницу, принять неверное архитектурное, продуктовое или эксплуатационное решение?** Если да, описание требуется обновить.

Запускать целевую LLM-генерацию, когда изменились:

- назначение или ответственность модуля;
- пользовательский сценарий, бизнес-правило либо state contract;
- архитектурная граница, поток данных, навигация или жизненный цикл;
- публичный API, внешний контракт или взаимодействие подсистем;
- onboarding, сборка, запуск либо существенная ADR/README/спецификация;
- состав подсистемы: добавлен, удалён или перенесён концептуально значимый компонент;
- истинность существующей страницы: найден устаревший, ошибочный или загрязнённый текст.

Обычно не запускать LLM только из-за форматирования, тестов существующего поведения, локального bug fix без изменения контракта, внутреннего refactoring, приватного rename, generated files или локализации без изменения сценария. Количество файлов и коммитов само по себе ничего не решает.

### Частично обновить model-written страницы

Если смысл изменила одна фича или подсистема, сначала обновить структурный слой через `update --index-only`, затем проверить точный LLM-план:

```bash
repowise generate . \
  --path <PATH_PREFIX_1> \
  --path <PATH_PREFIX_2> \
  --cascade full \
  --provider <PROVIDER> \
  --model <MODEL> \
  --reasoning <REASONING> \
  --concurrency <CONCURRENCY> \
  --dry-run
```

После проверки выбранных model page types, cascade и оценки повторить без `--dry-run`. Сохранить показанные dry-run общее количество, точные page IDs и добавленные cascade-зависимости: они нужны для последующей сверки checkpoint. Удалить второй `--path`, если область одна. Dry-run подтверждает selection и cost, но не строит runtime file contexts; выбранная им страница всё ещё может быть пропущена до создания generation coroutine.

В pinned fork `35ea9f92` planner, scope, cost estimate и реальный generator используют одну near-clone-deduplicated выборку. `generate --all` планирует только актуальные generatable concept IDs и исключает retired/obsolete сохранённые IDs; остальные scope-режимы пересекаются с той же текущей выборкой, а явно запрошенный устаревший ID сообщается отдельно. Это устраняет planner-only near-clone страницы, но реальные runtime gates — например отсутствие file contexts или onboarding gate — всё ещё могут дать явный skip.

`update --docs` не является полной или целевой генерацией концептуальной wiki. Он только переопределяет сохранённый `deterministic` / `No prose` режим для одного инкрементального `update`; в 0.48.0 этот update всё равно использует `file_pages_only=True`. Флаг не заменяет `generate --path`, `generate --page`, `generate --unwritten` либо `generate --all`. Для текущих LLM-backed проектов с сохранённым docs mode он не нужен.

### Как доказать обновление LLM-описаний

Перед реальным `generate` или `restyle` сохранить UTC-границу. Делать это после проверки dry-run и непосредственно перед model-вызовами:

```bash
REPOWISE_GENERATION_STARTED_AT="$(date -u '+%Y-%m-%d %H:%M:%S')"
```

После завершения проверить фактически сохранённые concept rows:

```bash
sqlite3 -header -column .repowise/wiki.db "
SELECT id, page_type, target_path, provider_name, model_name, updated_at
FROM wiki_pages
WHERE page_type IN (
  'module_page', 'repo_overview', 'architecture_diagram', 'onboarding'
)
AND updated_at >= '$REPOWISE_GENERATION_STARTED_AT'
ORDER BY page_type, id;
"
```

Сопоставить IDs, типы и количество строк с dry-run plan и итогом реальной команды. Для 0.48 отсутствие ожидаемых concept rows блокирует утверждение об обновлении. Для 0.55 timestamp-запрос доказывает written rows; отдельно подтвердить unchanged IDs исходным content/hash и native outcome текущего запуска. Их прежний timestamp не означает пропуск. После plain `update` отсутствие refreshed existing concept rows ожидаемо.

После каждого реального `generate` — и после `restyle`, если эта команда создала файловый checkpoint, — отдельно проверить точный `.repowise/jobs/<job-id>.json`. Это основной execution record: последняя SQL-строка `generation_jobs` может относиться к структурному `cli_update`, а не к проверяемому запуску.

Точный checkpoint определять по выведенному job ID/path. Если команда его не показала — сопоставить кандидаты по UTC-границе, `repo_path`, provider, model и plan; нельзя выбирать файл только потому, что он самый новый. Сохранить approved dry-run IDs в отдельном текстовом файле по одному ID на строку. Если dry-run показал только counts, честно указать, что конкретный пропущенный ID из одного checkpoint восстановить нельзя.

Проверка checkpoint и plan:

```bash
python3 - '<JOB_JSON>' '<PLANNED_PAGE_IDS_FILE>' <<'PY'
import json
import sys
from pathlib import Path

job_path = Path(sys.argv[1])
plan_path = sys.argv[2]
job = json.loads(job_path.read_text())

completed = set(job.get("completed_page_ids") or [])
failed = set(job.get("failed_page_ids") or [])
raw_skipped = job.get("skipped_page_ids") or []
skipped = set(raw_skipped.keys() if isinstance(raw_skipped, dict) else raw_skipped)
skip_reasons = job.get("skip_reasons") or {}

total = int(job.get("total_pages") or 0)
completed_count = int(job.get("completed_pages") or len(completed))
failed_count = int(job.get("failed_pages") or len(failed))
raw_skipped_count = job.get("skipped_pages")
skipped_count = raw_skipped_count if isinstance(raw_skipped_count, int) else len(skipped)
unaccounted_count = total - completed_count - failed_count - skipped_count

planned = None
if plan_path != "-":
    planned = {
        line.strip()
        for line in Path(plan_path).read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

accounted_ids = completed | failed | skipped
unaccounted_ids = sorted(planned - accounted_ids) if planned is not None else []
unexpected_ids = sorted(accounted_ids - planned) if planned is not None else []

print(f"job={job_path}")
print(f"job_id={job.get('job_id')} status={job.get('status')}")
print(
    "counts: "
    f"planned={total} completed={completed_count} failed={failed_count} "
    f"skipped={skipped_count} unaccounted={unaccounted_count}"
)
print(
    "id_lists: "
    f"completed={len(completed)} failed={len(failed)} skipped={len(skipped)} "
    f"planned={'unknown' if planned is None else len(planned)}"
)
for label, values in (
    ("failed", sorted(failed)),
    ("unaccounted", unaccounted_ids),
    ("unexpected", unexpected_ids),
):
    for page_id in values:
        print(f"{label}: {page_id}")
for page_id in sorted(skipped):
    print(f"skipped ({skip_reasons.get(page_id, 'reason unavailable')}): {page_id}")
print(f"error_message={job.get('error_message')!r}")

partial = (
    job.get("status") != "completed"
    or failed_count > 0
    or skipped_count > 0
    or unaccounted_count != 0
    or bool(unaccounted_ids)
    or bool(unexpected_ids)
    or (planned is not None and len(planned) != total)
    or completed_count != len(completed)
    or failed_count != len(failed)
)
print(f"accounting={'PARTIAL' if partial else 'COMPLETE'}")
PY
```

Обязательный invariant: `planned = completed + failed + skipped`. Pinned fork сохраняет `skipped_pages`, `skipped_page_ids` и `skip_reasons` и перед завершением относит к одному из исходов каждый planned ID. Положительный `unaccounted` count, строка `unaccounted: <page-id>` либо расхождение counters и ID lists теперь является регрессией и частичным результатом, даже если exit code равен нулю. Старые checkpoints без skipped ID lists по-прежнему сверять с сохранённым dry-run plan. Причину skip брать из `skip_reasons`; не выводить `no_file_contexts` только из count mismatch.

SQL `generation_jobs` использовать только как дополнительное свидетельство. Запрашивать `json_extract(config_json, '$.source')` и timestamps; строка без доказанной связи с текущей командой либо с `source=cli_update` не описывает реальный `generate` и не отменяет файловый checkpoint.

Для заранее известных страниц использовать повторяемый `--page <page-id>`: он точнее path prefix, который может выбрать вложенные подсистемы. Сначала проверить план:

```bash
repowise generate . \
  --page <PAGE_ID_1> \
  --page <PAGE_ID_2> \
  --cascade full \
  --provider <PROVIDER> \
  --model <MODEL> \
  --reasoning <REASONING> \
  --concurrency <CONCURRENCY> \
  --dry-run
```

Dry-run может добавить к известным IDs model-written dependents. Показать пользователю их IDs/типы и итоговое количество и сохранить их как approved plan: это dependency-consistent расширение плана, а не «ровно известные страницы». Если такое расширение ещё не разрешено, остановиться до реального запуска. После одобрения плана сохранить `REPOWISE_GENERATION_STARTED_AT` и повторить без `--dry-run`. Если `--cascade none` либо `dependents` сообщает, что зависимые страницы будут только помечены stale, использовать `--cascade full` или заранее согласовать отдельное восстановление этих страниц. Успешный dry-run не доказывает, что level builder сможет собрать file contexts для каждой страницы во время реального запуска.

### Частичный результат: fail-closed без остановки диагностики

Частичным считать любой из результатов:

- exit code не равен нулю;
- число или IDs сохранённых страниц не совпадают с одобренным dry-run plan и это не объясняется proven unchanged outcomes 0.55;
- появились незапланированные страницы;
- точный `.repowise/jobs/*.json` checkpoint содержит failed/skipped, положительный inferred `unaccounted` либо несогласованные counters и ID lists;
- matching SQL `generation_jobs.failed_pages > 0`, degraded/stale либо persistence warning;
- после генерации осталось подтверждённое загрязнение.

Fail-closed останавливает новые мутации, а не диагностику. Без нового разрешения обязательно продолжить read-only postchecks:

1. Сохранить исходную команду, stdout/stderr, exit code, dry-run counts/IDs, точный job ID/path и исходный `REPOWISE_GENERATION_STARTED_AT`.
2. Проверить exact file checkpoint скриптом выше. Он первичен для реального `generate`/`restyle`.
3. Проверить весь фактически сохранённый scope timestamp/SQL-запросом выше.
4. Выполнить прямой contamination audit из раздела 10, включая успешно сохранённые страницы.
5. Выполнить `repowise status` и полный `repowise doctor` без `--repair`.
6. Проверить текущую строку пропущенной страницы, её версии и дополнительные SQL generation jobs:

```bash
sqlite3 -header -column .repowise/wiki.db "
SELECT id, page_type, target_path, provider_name, model_name,
       freshness_status, version, created_at, updated_at, LENGTH(content) AS content_bytes
FROM wiki_pages
WHERE id = '<MISSING_PAGE_ID>';
"

sqlite3 -header -column .repowise/wiki.db "
SELECT page_id, version, page_type, provider_name, model_name, archived_at
FROM wiki_page_versions
WHERE page_id = '<MISSING_PAGE_ID>'
ORDER BY archived_at DESC
LIMIT 10;
"

sqlite3 -header -column .repowise/wiki.db "
SELECT id, json_extract(config_json, '$.source') AS source,
       status, total_pages, completed_pages, failed_pages,
       error_message, created_at, started_at, finished_at
FROM generation_jobs
ORDER BY created_at DESC
LIMIT 5;
"
```

SQL-строку считать относящейся к текущей реальной генерации только при совпадении source/timestamps/provider/model. В частности, `source=cli_update` — другой structural run, даже если это самая новая строка.

После этих проверок классифицировать причину: explicit или inferred build-time skip, provider/generator failure, checkpoint/persistence failure, неверная timestamp-граница либо пока неизвестно. Не называть unaccounted страницу «неточной плановой оценкой» без прямого доказательства.

До завершения диагностики не запускать новый `generate`, `restyle`, `update`, `reindex`, hook или repair. Если подтверждён реальный пропуск, можно подготовить новый точный `--page <MISSING_PAGE_ID> --cascade full --dry-run`, показать весь cascade scope и отдельно получить разрешение на реальную recovery-команду. Но dry-run снова проверит только selection/cost: при `skipped_no_file_contexts` или согласующемся с ним inferred unaccounted skip нельзя повторять идентичную реальную команду, пока не исправлена причина selection/context либо не доказан другой рабочий обход. Частичный результат не разрешает автоматический retry, но никогда не разрешает пропустить read-only проверки.

Текущий patched RepoWise обеспечивает implementation invariant `planned = completed + failed + skipped`: checkpoint сохраняет skipped page IDs и причины, а CLI при частичном результате отдельно показывает generated/failed/skipped и не пишет `every page is now written`. Любой новый silent drop между planner и coroutine считать регрессией.

Patched update дополнительно гарантирует:

- config-only изменение пересчитывает health и завершает работу, а config+source после health rescore продолжает graph/index/page update;
- `last_sync_commit` и `last_docs_commit` не продвигаются до успешной соответствующей persistence;
- `--dry-run` показывает и health rescore, и план страниц, не меняя state;
- stale structural file pages восстанавливаются обычным `update --index-only` даже при неизменном Git HEAD, без обращения к model provider;
- ошибка renderer, SQL, FTS или vector persistence оставляет страницу stale для повторной попытки;
- отсутствующие project-local VS Code MCP/recommendation файлы не создаются во время update.

В RepoWise 0.48 эти гарантии распространяются и на `update --full --dry-run`: он показывает single-repo fast-to-full план без LLM-вызовов и записей в vector store. `init --dry-run` отличается: он не пишет wiki/database, но может создать recoverable ingestion/session caches внутри `.repowise`.

Даже если в `.repowise/config.yaml` уже сохранено `editor_files.agents_md: false`, рецепты явно передают `--no-agents`, чтобы обновление RepoWise не меняло пользовательский `AGENTS.md`.

Если прежний unpatched update ошибочно продвинул state и следующий запуск отвечает `Already up to date`, сначала определить последний commit, содержимое которого действительно попало в индекс, и проверить recovery-план без LLM:

```bash
repowise update . --no-workspace --no-agents --index-only \
  --since <last-actually-indexed-commit> --dry-run
repowise update . --no-workspace --no-agents --index-only \
  --since <last-actually-indexed-commit>
repowise doctor
```

`--since` не выбирать наугад: он намеренно переигрывает весь диапазон до текущего HEAD. После structural recovery применить критерий смыслового устаревания выше и при необходимости отдельно выполнить `generate --path`. `doctor` должен показывать `0 stale` и drift `0.0%`.

### Заполнить отсутствующие subsystem-страницы

Если генерация была пропущена, прервана или часть model-written страниц осталась outline/template, сначала проверить только ненаписанные концептуальные страницы:

```bash
repowise generate . \
  --unwritten \
  --cascade none \
  --provider <PROVIDER> \
  --model <MODEL> \
  --reasoning <REASONING> \
  --dry-run
```

Если план корректен, повторить без `--dry-run`. `--unwritten` не обновляет уже написанную, но устаревшую страницу; для неё использовать `generate --path`. Для синхронизации изменённого кода использовать `update`.

### Полностью сменить стиль существующей wiki

`restyle` перегенерирует всю wiki, а не только отсутствующие или изменившиеся страницы, поэтому может снова занять много времени:

```bash
repowise restyle caveman \
  --provider codex_cli \
  --model codex_cli/gpt-5.6-luna \
  --reasoning low \
  --concurrency 1
```

Для `codex_cli` начинать с `--concurrency 1`; увеличивать только если предыдущие прогоны не дают timeout. Patched `restyle` показывает Rich-progress, сохраняет страницы по мере завершения и записывает итоговые provider/model/reasoning/style/tokens в state. Предупреждение старой версии `coroutine 'make_cost_tracker' was never awaited` исправлено; cost tracker не должен скрывать прогресс или мешать persistence. Если процесс остановлен, повтор той же команды переиспользует уже сохранённые страницы и продолжает работу, а не начинает весь generation с нуля.

Не использовать `restyle` или `update --full` только ради добавления prose в `No prose` индекс: для этого точнее `generate --unwritten --cascade none`. `restyle` нужен именно для полной смены голоса/формата уже существующей wiki.

## 9. Проверка состояния и поиск

```bash
repowise status
repowise doctor
```

Интерпретировать результат буквально:

- `Last sync commit = HEAD`, `0 stale` и `Drift=0.0%` подтверждают только эти отдельные проверки;
- exit code `0` не означает, что весь `doctor` успешен;
- полностью успешный результат заканчивается `All checks passed!`;
- если финальная строка — `Some checks failed.`, сохранить и сообщить все `WARN`/`FAIL`, даже когда stale и drift равны нулю;
- предупреждение о новой версии или optional hosted account отделять от ошибок базы, persistence, MCP registration, stale pages и vector drift, но не называть весь `doctor` полностью прошедшим.

Отдельная операция может быть доказанно успешной, если единственная оставшаяся проблема `doctor` — не связанный с ней optional/version warning. В таком случае сообщить успех операции с оговоркой и точный warning; не писать, что весь `doctor` прошёл.

### Clean reindex для orphaned vectors

RepoWise 0.48 `reindex` не очищает существующую LanceDB: он upsert-ит актуальные SQL IDs, поэтому `doctor: orphaned > 0` после обычного reindex останется без изменений. Для orphaned-векторов нужен recoverable clean reindex. Сначала получить явное разрешение и выбрать новый backup path вне репозитория:

```bash
cd /путь/к/нужному/checkout

REPOWISE_VECTOR_BACKUP="/абсолютный/путь/вне/репозитория/lancedb-$(date '+%Y%m%d-%H%M%S')"
test -d .repowise/lancedb
test ! -e "$REPOWISE_VECTOR_BACKUP"
mkdir -p "$(dirname "$REPOWISE_VECTOR_BACKUP")"
mv .repowise/lancedb "$REPOWISE_VECTOR_BACKUP"

repowise reindex . --embedder <EMBEDDER>
repowise doctor
```

Успех: eligible SQL/Vector sets синхронны, orphaned `0`, drift `0.0%`; raw SQL/Vector count equality относится только к historical 0.48 recipe. В 0.55 excluded/below-floor rows не являются missing vectors и не требуют reindex при синхронном eligible наборе. Backup не удалять до этой проверки. Если reindex завершился ошибкой, не удалять и не перезаписывать backup и не запускать `doctor --repair`; сохранить новый частичный vector directory и сначала согласовать восстановление.

Накопительный `Total tokens` из `status` не доказывает model-вызов в последней команде. Для утверждения об обновлении concept prose использовать timestamp/SQL-проверку из раздела 8.

Локальный полнотекстовый поиск:

```bash
repowise search "authentication flow"
```

Поиск символа:

```bash
repowise search --mode symbol "ChatViewModel"
```

История зарегистрированного расхода модели:

```bash
repowise costs
repowise costs --by model
```

Опциональный локальный dashboard:

```bash
repowise serve
```

Команда запускает API и локальный web UI; на первом запуске UI скачивается и кэшируется (около 50 MB). Docker для этого не требуется. Это не обязательный шаг установки и не нужно оставлять запущенным для Codex MCP.

Дополнительные аналитические команды:

```bash
repowise dead-code
repowise dead-code --safe-only
repowise risk HEAD~1..HEAD
```

Даже `dead-code --safe-only` и risk score являются сигналами RepoWise, а не разрешением удалять код или утверждать корректность изменения без проверки проекта.

`doctor --repair` не является обычным шагом установки или обслуживания. Если `doctor` найдёт проблему, сначала сохранить его полный вывод и разобраться в конкретной проверке; автоматический repair запускать только как осознанное устранение уже понятной неисправности.

## 10. Использование через Codex

1. Проверить, какой RepoWise MCP сейчас зарегистрирован: single-repo без фиксированного path или workspace с фиксированным `<WORKSPACE_ROOT>`.
2. В single-repo режиме открыть задачу Codex именно в нужном checkout и убедиться, что для него выполнены `repowise init` и актуальный `repowise update --index-only`.
3. В workspace режиме проверить `list_repos` и обращаться к нужному repo по alias; cwd задачи и прикреплённые папки ChatGPT сами alias не выбирают.
4. Агент может вызвать RepoWise самостоятельно, когда сочтёт его полезным, но автоматический вызов не гарантирован. Если RepoWise нужен обязательно, прямо указать это в запросе, например:

```text
Используй RepoWise, чтобы показать архитектуру этого участка и зависимости символа X.
```

или:

```text
Перед изменением проверь через RepoWise связанные компоненты и blast radius файла Y.
```

В каждый момент используется одна глобальная RepoWise MCP registration. В single-repo режиме она обслуживает индекс из cwd задачи. В workspace режиме она указывает на фиксированный root и обслуживает все aliases; отдельная MCP-запись для каждого repo не нужна.

В single-repo режиме новая задача с другим root нужна для другого индекса. В workspace режиме смена root задачи не переключает RepoWise: repo выбирается параметром `repo=<alias>` в MCP-вызове. В обоих режимах список прикреплённых к проекту ChatGPT папок не меняет конфигурацию RepoWise.

### Быстрые и синтезирующие MCP-запросы

RepoWise экономит количество ручных чтений, но не гарантирует минимальную задержку каждого вызова:

- repo/list, symbol, source, callers/dependencies и другие структурные запросы обычно являются быстрым индексным маршрутом;
- `get_answer` и похожий synthesis могут запускать дополнительную агрегацию и на холодном старте занимать минуты;
- не объединять быстрые структурные и медленный синтезирующий вызов в один параллельный пакет, если общий результат блокируется самым медленным запросом;
- `confidence: low` означает, что ответ нужно считать гипотезой и проверить по source/symbol-инструментам;
- `search_method: bm25`, `bounds: approximate`, truncation и stale warnings являются ограничениями полноты, а не доказательством отсутствия.

На локальном тесте старой сборки один холодный `get_answer` занял около 153 секунд и вернул `confidence: low`; это допустимая граница инструмента, а не причина использовать synthesis для каждого вопроса. Сначала запрашивать структуру и точные символы, synthesis — когда действительно нужна межстраничная сводка.

### Проверить wiki на старое загрязнение

Патч `657b3ca8` не позволяет новым Codex generation-вызовам склеивать промежуточные agent-команды с финальным текстом. Уже сохранённые до установки патча страницы автоматически не очищаются.

После generation проверять сохранённые `wiki_pages` напрямую: content и optional digest. Следующая SQLite-проверка открывает базу read-only без migrations, работает на 0.48 без digest и на 0.55 с digest. Не открывать старую базу новым CLI перед аудитом. Ranked search полезен для навигации, но может не показать все совпадающие строки и не заменяет SQL-аудит:

```bash
python3 - <<'PY'
import sqlite3
from pathlib import Path

# mode=ro avoids schema migration; never bootstrap this audit with a new CLI.
db_uri = Path(".repowise/wiki.db").resolve().as_uri() + "?mode=ro"
with sqlite3.connect(db_uri, uri=True) as db:
    db.row_factory = sqlite3.Row
    columns = {row[1] for row in db.execute("PRAGMA table_info(wiki_pages)")}
    fields = ["content"] + (["digest"] if "digest" in columns else [])
    markers = (
        "Сначала проверяю", "обязательные инструкции", "I am still working",
        "I need to inspect", "I will inspect", "You are Codex",
        "AGENTS.md instructions",
    )
    print("audited_fields=" + ",".join(fields))
    print("digest=" + ("present" if "digest" in columns else "absent (legacy schema)"))
    query = "SELECT id, page_type, target_path, updated_at, " + ", ".join(fields)
    query += " FROM wiki_pages ORDER BY page_type, id"
    for row in db.execute(query):
        for field in fields:
            text = row[field] or ""
            matches = [marker for marker in markers if marker.lower() in text.lower()]
            if matches:
                print(dict(id=row["id"], page_type=row["page_type"],
                           target_path=row["target_path"], updated_at=row["updated_at"],
                           field=field, markers=matches))
PY
```

Дополнительный поиск:

```bash
repowise search "Сначала проверяю"
repowise search "обязательные инструкции"
repowise search "I need to inspect"
repowise search "I will inspect"
repowise search "You are Codex"
repowise search "AGENTS.md instructions"
```

Каждое SQL-совпадение проверить в указанном поле: фраза может быть легитимной частью проектной документации. Digest-only commentary является загрязнением даже при clean content. Marker scan лишь находит кандидатов; дополнительно проверить весь approved written/reused scope. Подтверждённое загрязнение отчётно фиксировать с page ID, path, type, field и `updated_at`. Оно останавливает новые mutation-команды, но не отменяет обязательные `status`, `doctor`, persistence/version/job queries на согласованном runtime и проверку остальных уже сохранённых страниц.

Для известного набора страниц использовать повторяемые `--page <page-id>` с `--cascade full`: сначала `--dry-run`, затем реальную команду с UTC-границей и проверкой persistence из раздела 8. Не переходить к `--all` только из-за нескольких известных страниц. `generate --all` или `restyle` нужен для широкого загрязнения всего prose-слоя и может быть долгим. Структурные file/symbol pages через `generate` не переписываются — они обновляются командой `repowise update`.

### Настройка проектного `AGENTS.md`

`AGENTS.md` не требуется для работы индекса или MCP. Его автоматическая генерация нужна только тогда, когда RepoWise должен сам добавить Codex готовые правила использования своих инструментов и актуальный снимок проекта.

Настройка хранится в `.repowise/config.yaml`:

```yaml
editor_files:
  agents_md: false
```

Поведение режимов:

- `repowise update --agents` — сохранить `agents_md: true` и после успешного update создать или обновить управляемый блок между `REPOWISE_AGENTS:START` / `REPOWISE_AGENTS:END`;
- обычный `repowise update` — следовать сохранённому значению;
- `repowise update --no-agents` — сохранить `agents_md: false` и не создавать/не обновлять управляемый блок.

При включённой генерации RepoWise сохраняет пользовательский текст вне маркеров: если маркеров нет, блок добавляется в конец существующего файла; если они есть, заменяется только содержимое между ними. `agents_md: false` прекращает обновление, но не удаляет уже добавленный блок.

Автоматическую генерацию имеет смысл включать, когда:

- в проекте нет собственного настроенного `AGENTS.md`;
- Codex является основным агентом, а RepoWise MCP доступен всем пользователям проекта;
- команда принимает генерируемые RepoWise-first routing/trust rules;
- model-written wiki предварительно проверена на загрязнённые или чужие инструкции.

Для зрелого проекта с собственными правилами Serena, Xcode MCP, context-mode и shell автоматический блок не включать: он дублирует маршрутизацию, может конфликтовать с обязательными правилами и добавляет быстро устаревающие architecture/health/hotspot summaries. Рекомендуемый вариант — оставить `agents_md: false` и вручную поддерживать только стабильные операционные правила RepoWise и Distill.

Минимальный ручной набор, который полезно адаптировать к существующему разделу приоритетов:

```markdown
- When Distill returns `[repowise#<ref>: N lines omitted]`, recover the stored
  output with `repowise expand <ref>` or filter it with
  `repowise expand <ref> -q <regex>` instead of rerunning the original command;
  Distill preserves the original command's exit code.
- Treat `callers_total` / `callers_truncated` as completeness signals; in
  PR-mode `get_risk`, read `directive` first, treat an empty `tests_to_run` as
  unknown coverage rather than no tests, and follow `successor_paths` after a
  tombstone.
- Treat RepoWise source, ranges, or symbol bodies marked `verified: true` as an
  already-performed read of the exact served bytes. Independently verify
  `bounds: "approximate"`, `_meta.stale_warning`, `search_method: "bm25"`, or
  `confidence: "low"`; `index_behind: true` alone does not invalidate verified
  live bytes. Read any missing body or surrounding context required for edits.
```

Эти правила дополняют, а не заменяют проектные границы: RepoWise не должен в одиночку доказывать отсутствие, безопасное удаление, полноту callers/dependents или успешность build/test/runtime-проверки.

Автоматическое обновление не включать по умолчанию: проверить существующие hooks/watch и отдельно согласовать их использование с пользователем.

## 11. Автоматическое обновление — пока не включать

Для выбранного режима `Everything` не рекомендуется запускать:

```bash
repowise hook install
repowise watch
```

Обе автоматизации используют сохранённый режим обновления; при `llm` это может приводить к незаметным обращениям к модели. Ручная команда `repowise update --index-only` оставляет расход под контролем.

Если post-commit hook был установлен случайно, удалить его из основного checkout:

```bash
cd /path/to/app
repowise hook uninstall
repowise hook status
```

Git hooks общие для linked worktree, поэтому отдельное удаление в `app-develop` не требуется.

Проверка после установки:

```bash
repowise hook status
```

Ожидаемый результат: `post-commit: not installed`.

### Distill rewrite hook в Codex

RepoWise 0.48 действительно поддерживает Codex. Предложение `Distill` во время `init` объединяет четыре автоматических hook-поведения:

- command rewrite через `repowise distill ...`;
- `read-skeleton` для полного чтения больших файлов;
- `search-digest` для поиска с большим числом совпавших файлов;
- `read-reread` для повторного чтения уже прочитанного неизменённого файла.

Это не часть индексации, semantic search или MCP и не требуется для работы RepoWise. После отказа все возможности можно включать отдельно командами `repowise hook read-skeleton`, `repowise hook search-digest`, `repowise hook read-reread`; command rewrite устанавливается через `repowise hook rewrite install`. Raw command output у Distill остаётся восстанавливаемым через `repowise expand`.

При установке rewrite RepoWise настраивает Claude Code, а при обнаруженном совместимом Codex CLI также добавляет `PreToolUse` entry в пользовательский `~/.codex/hooks.json` и managed Distill-awareness section в проектный `AGENTS.md`. Codex может попросить отдельно доверить новый hook через `/hooks`. Для command families с `permission: ask` Codex rewrite не применяется: protocol не умеет одновременно спросить разрешение и заменить команду.

Hook-файлы плагинов хранятся отдельно, но их поведение не изолировано. Сейчас Serena находится в пользовательском `hooks.json`, а context-mode — в собственном plugin `hooks.json`; при shell-вызове все совпавшие `PreToolUse` hooks всё равно участвуют в обработке одного события. Следовательно, проблема не сводится к тому, что несколько hooks записаны в одном JSON. Один файл влияет на порядок и удобство сопровождения, но отдельный plugin-файл не устраняет конкуренцию rewrites/deny/добавочного контекста.

Локальный сравнительный тест показал:

- RepoWise переписывает распознанные команды в `repowise distill ...`;
- Serena продолжает считать/ограничивать совпавшие поисковые команды;
- context-mode для части build-команд может вернуть конкурирующий `updatedInput`;
- `xcodebuild` и `swift` в текущем классификаторе RepoWise не покрыты;
- plain `rg` без `-n` даёт некачественный distill-результат.

Поэтому при обязательном context-mode автоматический Distill bundle пока не устанавливать: выбирать `n` либо передавать `--no-distill-hook`. При необходимости можно явно запускать отдельную шумную команду через `repowise distill ...`; это не меняет глобальную hook-цепочку. Проверка текущего состояния:

```bash
cd /path/to/app
repowise hook rewrite status
```

## 12. Обновление самого RepoWise

Обновление глобального CLI — отдельная пользовательская операция. Агент не должен запускать её из-за version warning, новой upstream-версии или обычного обслуживания проекта. Выполнять обновление может сам пользователь либо агент **только по явной просьбе пользователя**.

Официальный контракт описан в `docs/reference/UPGRADING.md`: обновить пакет, затем выполнить обычный `repowise update` в каждом существующем репозитории. Новая версия при открытии store автоматически применяет совместимые миграции, добавление колонок и необходимые backfill-операции; изолированный тест показал, что даже `status` может открыть и обновить schema. Поэтому backup должен предшествовать любой команде нового CLI. Отдельной migration-команды нет. Сам schema upgrade не требует documentation LLM; если изменился embedding model, RepoWise может отдельно потребовать/выполнить vector rebuild без prose-генерации.

В обычном случае не нужны `init --force` и полный `reindex`. Выполнять их только когда новая версия сама показывает точное уведомление о несовместимом store format, либо когда `doctor` подтверждает реальный vector drift/повреждение.

### Не потерять fork-патчи

Пока нужны локальные исправления, **не выполнять** обычные:

```bash
uv tool upgrade repowise
uv tool install --force repowise
```

Обе команды устанавливают официальный PyPI build и тем самым удаляют fork-патчи, даже если номер версии выглядит ожидаемо.

### Сначала сохранить индексы

До замены CLI сохранить workspace metadata и каждый индекс отдельно вне Git-репозиториев. Сделать это **до первого** запуска нового runtime: `status`, `doctor`, `update`, `serve`, `mcp` или preview могут открыть старую базу и применить совместимую schema migration. Блок backup ниже исторический; точные targets подтвердить перед отдельной разрешённой будущей миграцией 0.55.

```bash
REPOWISE_BACKUP_ROOT="/path/to/backups/repowise-$(date '+%Y%m%d-%H%M%S')"
mkdir -p "$REPOWISE_BACKUP_ROOT"

# Повторить для каждого подтверждённого repository и workspace.
ditto /path/to/repository/.repowise "$REPOWISE_BACKUP_ROOT/repository.repowise"
ditto /path/to/workspace "$REPOWISE_BACKUP_ROOT/workspace"
```

Сохранить каждый independent index до запуска его MCP новым runtime, даже если его активная миграция отложена. Не удалять backup, пока каждый открытый новой версией индекс не пройдёт `status` и полный `doctor`.

### Историческая установка / rollback проверенного patched build 0.48

```bash
uv tool install --force --python 3.13 \
  "repowise @ git+https://github.com/Kudrinetskiy/repowise.git@35ea9f923de5bb8a3da847284551316c2708190e"
repowise --version
uv tool list --show-paths --show-version-specifiers
```

Ожидаемая CLI-версия — `0.48.0`. Сохранить полный вывод `uv tool list`: именно pinned SHA доказывает fork build.

### Проверка локального fork перед отдельно разрешённой установкой

Следующий блок только обновляет локальный checkout fork. Сам fetch или текущий `main` не доказывают проверенный build и не разрешают установку; для неё использовать только опубликованную pinned-команду и отдельный запрос пользователя.

```bash
cd /path/to/repowise-fork
git fetch origin
git switch main
git log --oneline HEAD..origin/main
git pull --ff-only origin main
git rev-parse HEAD
```

Перед установкой нового HEAD проверить его diff и тесты. Не применять сохранённые site-packages-патчи поверх будущей версии вслепую: fork-коммиты теперь являются исходником и должны переноситься обычным Git rebase/cherry-pick с повторной проверкой.

### Последовательно мигрировать существующие индексы

Переинициализация не требуется. Сначала, пока ещё работает старая версия, зафиксировать Git HEAD/status всех repos, текущий MCP target и утверждённый workspace config. Если есть пользовательский WIP, не переключать ветку, не сбрасывать и не включать его в RepoWise maintenance без отдельного решения. При будущем явно разрешённом переходе 0.48 → pinned 0.55 после backup и установки не выполнять промежуточный `status`: переходить к выбранной migration-команде с `REPOWISE_SKIP_EDITOR_SETUP=1`. Первый доступ может мигрировать schema, включая `wiki_pages.digest`; опубликованный fork сам по себе не разрешает этот этап.

Порядок возврата MCP зависит от подтверждённой topology пользователя: все repositories каждого workspace должны открываться совместимым runtime. Independent indexes могут иметь собственные MCP; project-local override одного server id учитывать отдельно. После миграции регистрировать только выбранные aliases, без повторного `init`.

При будущей миграции другого существующего индекса сначала отключить его MCP, сделать полную проверенную копию `.repowise`, затем выполнить single-repo `update --no-workspace --index-only --no-agents`. Только после успешных `status` и `doctor` регистрировать готовый индекс в workspace через `workspace add ... --no-index`; default `workspace add` может запустить повторное индексирование и model docs.

Если все нужные индексы уже зарегистрированы в одном workspace, использовать один workspace-маршрут и затем проверить каждый repo:

```bash
repowise workspace list <WORKSPACE_ROOT>
REPOWISE_SKIP_EDITOR_SETUP=1 repowise update <WORKSPACE_ROOT> \
  --workspace --index-only --no-agents --dry-run
REPOWISE_SKIP_EDITOR_SETUP=1 repowise update <WORKSPACE_ROOT> \
  --workspace --index-only --no-agents
repowise doctor <WORKSPACE_ROOT> --workspace
repowise workspace list <WORKSPACE_ROOT>
```

Не считать этот режим выбранным только из-за нескольких папок ChatGPT. Если workspace отсутствует или пользователь сознательно сохраняет независимые индексы, обрабатывать репозитории по одному. Следующие блоки — общие single-repo рецепты; необходимость миграции определять по проверенному состоянию каждого индекса.

```bash
cd /path/to/independent-project
git rev-parse HEAD
REPOWISE_SKIP_EDITOR_SETUP=1 repowise update . \
  --no-workspace --index-only --no-agents --dry-run
REPOWISE_SKIP_EDITOR_SETUP=1 repowise update . \
  --no-workspace --index-only --no-agents
repowise status
repowise doctor
git rev-parse HEAD
git status --short -- AGENTS.md .vscode
```

```bash
cd /path/to/app-develop
git rev-parse HEAD
REPOWISE_SKIP_EDITOR_SETUP=1 repowise update . \
  --no-workspace --index-only --no-agents --dry-run
REPOWISE_SKIP_EDITOR_SETUP=1 repowise update . \
  --no-workspace --index-only --no-agents
repowise status
repowise doctor
git rev-parse HEAD
git status --short -- AGENTS.md .vscode
```

```bash
cd /path/to/app
git rev-parse HEAD
REPOWISE_SKIP_EDITOR_SETUP=1 repowise update . \
  --no-workspace --index-only --no-agents --dry-run
REPOWISE_SKIP_EDITOR_SETUP=1 repowise update . \
  --no-workspace --index-only --no-agents
repowise status
repowise doctor
git rev-parse HEAD
git status --short -- AGENTS.md .vscode
```

Первый `update --index-only` является штатной точкой автоматической миграции store и одновременно обновляет структурный индекс без documentation provider. Не заменять его `init --force`. Schema migrations и backfills выполняются при штатном открытии/обновлении; в 0.55 появляется `wiki_pages.digest`. Synthetic SQLite 0.48 → 0.55 проверяет сохранность prose/метаданных, digest default/backfill и повторное открытие; это не acceptance живых индексов и не доказательство PostgreSQL-миграции. Health автоматически пересчитывается на следующем update при изменении правил или fingerprint.

Dry-run в этом migration-рецепте остаётся обычным incremental `update --dry-run`. Это логическая проверка выбора страниц, а не универсальная гарантия побайтовой неизменности `.repowise`: в проверенном 0.40 запуск `update --index-only --dry-run` не менял `wiki.db` и `state.json`, но переписал parse/centrality caches и episodes, а также закрыл WAL/SHM. Если важны точные filesystem hashes, сначала сделать backup. В 0.48 также разрешён `update --full --dry-run`, но для миграции уже полных индексов он не нужен.

Критерии: `Last sync commit` равен текущему HEAD, `0 stale`, SQL/vector и SQL/FTS синхронны, drift `0.0%`, полный `doctor` заканчивается `All checks passed!`, Git HEAD и `AGENTS.md` не изменились. Если MCP зарегистрирован, новая строка `MCP server responds` должна быть `OK`: doctor действительно запускает сервер и проверяет JSON-RPC, а не только существование пути. Сравнить `.vscode` с preflight: patched update не создаёт отсутствующие файлы, но уже существующие integration-файлы может обновить. Если `doctor` рекомендует `reindex` или `init --force`, остановиться, сохранить полный вывод и согласовать операцию; не запускать её автоматически.

Если случайно был установлен stock build, просто повторить pinned Git-команду из начала этого раздела. Локальные индексы при переустановке CLI не удаляются.

### Перезапустить Codex

После отдельно разрешённой замены tool и проверки индексов полностью перезапустить Codex, чтобы старый MCP-процесс завершился и новый запуск использовал выбранный pinned runtime. Повторять `codex mcp add` не нужно, если проверенная регистрация всё ещё использует стабильный путь `~/.local/bin/repowise`. Подготовка fork 0.55 не требует перезапуска действующего MCP 0.48.

Когда upstream выпустит более новую версию, сначала воспроизвести каждый из одиннадцати рабочих fixes на чистом новом теге. Только после этого обновить fork, убрать доказанно лишние коммиты, адаптировать остальные, повторить тесты и изменить pinned commit в этой инструкции.

### Исторический smoke опубликованного 0.48 pin без глобальной установки

Эта команда создаёт временное окружение и не заменяет установленный tool:

```bash
uv tool run --python 3.13 --from \
  "repowise @ git+https://github.com/Kudrinetskiy/repowise.git@35ea9f923de5bb8a3da847284551316c2708190e" \
  repowise --version
```

## 13. Короткий ежедневный чек-лист

Сначала определить фактический режим по 5A.1-5A.2. Для одного независимого repo:

```bash
cd /путь/к/нужному/checkout
repowise update . --no-workspace --no-agents
repowise status
repowise doctor
```

Для всех repos утверждённого workspace:

```bash
repowise update <WORKSPACE_ROOT> --workspace --no-agents
repowise workspace list <WORKSPACE_ROOT>
repowise doctor <WORKSPACE_ROOT> --workspace
```

Для одного alias утверждённого workspace:

```bash
repowise update <WORKSPACE_ROOT> --repo <ALIAS> --no-agents
repowise workspace list <WORKSPACE_ROOT>
repowise doctor <WORKSPACE_ROOT> --workspace
```

После этого пользоваться RepoWise через MCP: в single-repo режиме из задачи с нужным root, в workspace режиме — с явным repo alias. Эти plain `update` синхронизируют структурный слой; не объявлять concept prose обновлённой по общим page counters.

Если старое LLM-описание способно привести агента к неверному решению, выполнить целевую генерацию:

```bash
# single-repo structural step; in a workspace use 5A.6 with --repo <ALIAS> --index-only
repowise update . --no-workspace --no-agents --index-only
repowise generate . \
  --path <ИЗМЕНИВШАЯСЯ_ОБЛАСТЬ> \
  --cascade full \
  --provider <PROVIDER> \
  --model <MODEL> \
  --reasoning <REASONING> \
  --dry-run
```

После проверки плана повторить `generate` без `--dry-run`. `generate --all` выбирать только для явного full-project refresh, смены стиля/модели или очистки подтверждённого загрязнения; soft reset, большое число коммитов или обычное обновление ветки сами по себе не являются причиной.

Непосредственно перед реальным `generate` сохранить `REPOWISE_GENERATION_STARTED_AT`, затем выполнить timestamp/SQL-проверку persistence, прямой contamination audit, `status` и полный `doctor`. Успех model-written обновления подтверждается сохранёнными concept rows и проверенным содержимым, а не строками `Generating pages` / `Pages updated`.

Если реальный результат частичный, всё равно завершить эти read-only postchecks и диагностические SQL-запросы из раздела 8. До отдельного разрешения остановить только новые mutation-команды и recovery retry.

## Источники

- Проверенный runtime fork: `https://github.com/Kudrinetskiy/repowise/tree/428c62fd10c5069b1c2dba5c68145673bb944338`
- Upstream base: `repowise-dev/repowise@e829775bfd18f22ff2f9522d514d3b94c1fde2b6` (`v0.55.0`).
- Официальный upgrade contract: `https://github.com/repowise-dev/repowise/blob/v0.55.0/docs/reference/UPGRADING.md`
- Контракты команд проверять по выбранному pinned runtime: `repowise init --help`, `repowise update --help`, `repowise generate --help`, `repowise restyle --help`, `repowise reindex --help`, `repowise workspace --help`, `repowise doctor --help`, `repowise mcp --help`.
