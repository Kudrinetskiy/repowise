# RepoWise 0.59: patched-установка и рабочие рецепты

## Область и источник истины

Цель — patched 0.59.0 поверх upstream v0.59.0, не описание текущей установки конкретного пользователя. Release pin: `03fb8850b8b0f9912c077e41c331a902ed82e895`. Это проверенный CLI code-коммит; main может содержать отдельно проверенные изменения skill/helper/инструкции без изменения установленного CLI. Не подставлять изменяемый main. Проверки пакета не доказывают исправность живых индексов. Исторические результаты 0.48/0.55 сюда не переносятся как текущий PASS.

Опции сверены с рабочим CLI 0.59.0: init, update, generate, restyle, reindex, doctor, workspace add. Перед выполнением проверить фактически выбранный runtime и его help. Полные готовые рецепты, accounting-скрипт и SQLite contamination audit находятся в основном SKILL.md; эта справка объясняет установку и выбор маршрута.

Skill остаётся explicit-only. Разрешение исследовать состояние не разрешает устанавливать tool, открывать старую базу новой версией, регистрировать MCP, менять hooks, запускать reindex или LLM generation. Каждую мутацию выполнять только в согласованном объёме. Не включать автоматизацию вслед за version warning.

Все пути /path/to/... и параметры в угловых скобках — placeholders: разрешить их до исполнения. Provider/model/reasoning/style/concurrency брать из выбранного repo или явного решения пользователя. Ни Codex, ни большая модель, ни Ollama не являются обязательными defaults.

## Содержание

1. Inspection и выбор режима
2. Установка и upgrade CLI
3. Независимый init и embedder
4. Git exclude и editor/hook policy
5. MCP и workspace
6. Worktree и переписанная история
7. Update и model-written prose
8. Acceptance, accounting и contamination
9. Vector repair и безопасное продолжение

## 1. Inspection прежде установки

В каждом явно включённом в задачу repo определить canonical root, HEAD, WIP, существующие .repowise/state.json, config.yaml, wiki.db, lancedb и пользовательские editor files. Не исследовать произвольные соседние каталоги.

```bash
cd /path/to/repository
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --short
repowise --version
repowise telemetry status
codex mcp list
command -v ollama >/dev/null 2>&1 && ollama list
```

Показывать только имена/наличие API-key variables, не значения. Из .env читать только нужные несекретные selectors/model. Наличие Ollama-модели не выбирает её автоматически.

Если текущий runtime уже совместимо обслуживает существующий индекс, проверить status и полный doctor. При здоровом индексе повторный init не нужен. Частичная .repowise может быть resumable init или пользовательским scaffold; её нельзя удалять по имени каталога. Schema error после upgrade диагностировать, а не маскировать init --force.

До первого открытия старого индекса новым runtime согласовать preservation/backup policy: даже status, doctor, preview или запуск MCP могут применить additive schema migrations. SQLite mode=ro audit не требует запуска нового CLI. Не создавать копии checkout/workspace без отдельного разрешения.

Сначала определить single-repo или workspace:

- один repo без утверждённого workspace — намеренный --no-workspace;
- все зарегистрированные repos — --workspace;
- один alias workspace — --repo <ALIAS>;
- несколько прикреплённых к ChatGPT/Codex папок не создают RepoWise workspace;
- generate выполняется для конкретного repo, не всего workspace.

## 2. Установка и upgrade CLI

Только после явной просьбы пользователя, проверки pin, действующих MCP и preservation policy:

До первого открытия любого старого store новым runtime — включая status, doctor, preview и MCP — определить все действующие RepoWise MCP, hooks/watchers и другие процессы, которые могут обращаться к индексам в согласованном scope. Согласовать их временную остановку или изоляцию от этих store; сначала проверить точные процессы/маршруты и полномочия, затем подтвердить, что старый runtime больше не имеет активного доступа и не перезапустится автоматически во время migration. Не завершать посторонние процессы и не менять MCP/hooks без разрешения. Если изоляция не доказана или не разрешена, остановиться до первого new-runtime access; не подменять этот gate финальным reload клиента.

```bash
uv tool install --force --python 3.13 \
  "repowise @ git+https://github.com/Kudrinetskiy/repowise.git@03fb8850b8b0f9912c077e41c331a902ed82e895"
repowise --version
uv tool list --show-paths --show-version-specifiers
```

Ожидаемый номер версии — 0.59.0. Сам номер не доказывает fork: проверить direct_url.json установленного distribution, где vcs_info.commit_id должен равняться утверждённому полному SHA. Команду с неразрешённым pin исполнять нельзя. Публикация fork не устанавливает runtime и не мигрирует индексы.

Не заменять эту команду uv tool upgrade repowise, PyPI install, текущим main или локальным ".". Не удалять старое tool-окружение заранее. Если uv отсутствует, отдельно согласовать его установку; не устанавливать Homebrew/gh/дополнительные инструменты как побочный эффект.

После upgrade использовать согласованный structural migration для существующих индексов, не новый init и не безусловный reindex:

```bash
REPOWISE_SKIP_EDITOR_SETUP=1 repowise update /path/to/repository \
  --no-workspace --index-only --no-agents --dry-run
REPOWISE_SKIP_EDITOR_SETUP=1 repowise update /path/to/repository \
  --no-workspace --index-only --no-agents
repowise status /path/to/repository
repowise doctor /path/to/repository --format json
```

Preview уже открывает store; preservation и old-process isolation должны быть решены до него. При workspace использовать соответствующий --workspace/--repo маршрут. Не включать WIP через --working-tree без отдельного согласования.

До/после сравнить Git HEAD/WIP, модельные content/digest/model/timestamps/tokens и docs pointer, если их сохранность является требованием. Structural refresh может использовать embeddings, но не должен выдавать это за prose generation. При ошибке не запускать старый runtime на уже мигрированном store.

После разрешённой установки и проверок отдельно перезагрузить клиент/MCP по согласованию и восстановить только одобренные маршруты уже на проверенном новом runtime. Проверить фактический список инструментов и маршрутизацию: старая серверная сессия не становится новой только от изменения CLI на диске. Старые процессы не возвращать к мигрированным store.

Telemetry — отдельная настройка пользователя. При выбранном отключении: repowise telemetry disable, затем telemetry status.

## 3. Независимый init и embedder

После inspection и подтверждённого отсутствия полноценного индекса предложить два независимых решения: интерактивная или явная установка; embedding search. Уже сделанный выбор повторно не спрашивать.

0.59 использует plan screen: Enter запускает показанный план, m меняет model/documentation selection, e редактирует advanced options, q — выход. Условный пункт s переключает this-repo-only/global setup, а не настройки. Читать реальные подписи; не учить пользователя всегда выбирать старые номера 1/2/3 или Advanced. Не отвечать за пользователя. Для embedder проверить доступный edit flow либо передать явно выбранный --embedder; не обещать отдельный вопрос в любом режиме.

Embedder пишет поисковые векторы, provider/model пишет prose; Distill сжимает tool output и не относится к semantic search.

- mock — full-text/структура работают, полноценной semantic similarity нет;
- ollama — локальные embeddings; нужна запущенная Ollama с выбранной embedding-моделью;
- hosted gemini/openai/openrouter/edenai — соответствующие credentials и одобрение передачи текста/расходов;
- auto — разрешать по текущему repo/config/env; проверить фактический pin после операции.

init --embedder принимает конкретное значение; для auto/wizard опустить флаг. reindex отдельно поддерживает auto и может предложить заменить keyless mock, поэтому не считать auto обещанием навсегда сохранить mock.

Если пользователь выбрал конкретно mxbai-embed-large:latest, проверить ollama list и согласовать pull при отсутствии. Только затем сохранить OLLAMA_EMBEDDING_MODEL в .repowise/.env с owner-only permissions, не печатая secrets. Существующую другую строку не дублировать и не перезаписывать без решения. Не выполнять этот блок при выборе mock/hosted/auto.

Независимый cold init, интерактивно:

```bash
repowise init /path/to/repository \
  --no-workspace --no-seed \
  --no-claude-md --no-agents --no-codex \
  --no-distill-hook --no-hook --no-editor-setup
```

При явном structural варианте добавить --no-prose и выбранный --embedder; при необходимости сначала --dry-run. --mode fast означает индекс без documentation, а --no-prose standard строит documentation из кода без prose LLM; не путать их.

При явном model-written варианте добавить --prose и уже выбранные --provider, --model, --reasoning, --wiki-style, --concurrency, --embedder. Сначала --dry-run; реальную команду выполнить после одобрения плана/стоимости, заменив --dry-run на --yes. Не выдавать безусловный пример с конкретной моделью за пользовательское решение.

Для ephemeral credentials дополнительно использовать --no-save-key или REPOWISE_NO_SAVE_KEY=1: 0.59 по умолчанию может сохранять использованный ключ в .repowise/.env. Не менять существующую credential policy молча.

При interruption сохранить checkpoint; init --resume запускать в том же checkout с проверенными настройками и прежними opt-outs. Не переносить resume state в другой worktree.

## 4. Git exclude и editor/hook policy

Локальный индекс не должен случайно попасть в commit. После разрешения на локальную настройку использовать git rev-parse --git-path info/exclude и добавить .repowise/; .mcp.json исключать, если он действительно локальный. Проверить git check-ignore и git status. Не менять общий .gitignore и не объявлять любой командный .mcp.json личным файлом без inspection.

Current --no-editor-setup покрывает machine registration, project editor files и post-commit hook. Явные --no-claude-md --no-agents --no-codex --no-distill-hook --no-hook остаются defense in depth. REPOWISE_SKIP_EDITOR_SETUP=1 действует и на refresh. Отказ не удаляет уже существующие integration files: их удаление требует отдельного решения.

init/update рецепты сохраняют --no-agents. generate/restyle этого флага не имеют и не создают AGENTS.md. Проверять пользовательские файлы относительно preflight, не только факт их наличия.

Не включать hook install, watch или Distill bundle автоматически. Post-commit update может обращаться к provider для вспомогательной работы; отсутствие прямой API-цены не означает отсутствие расхода лимитов. Не удалять чужой hook как «исправление» без inspection/approval.

Ручной repowise distill допустим только в рамках локальных routing rules. При [repowise#<ref>: ... omitted] раскрывать repowise expand <ref>, не повторять исходную команду. Не включать автоматический rewrite ради одного запроса.

## 5. MCP и workspace

До регистрации проверить действующий codex mcp list и exact root. Если пользователь выбрал single-repo cwd routing, после разрешения зарегистрировать repowise mcp; для фиксированного repo добавить его путь, для workspace — exact workspace root. Не удалять существующую запись до проверки её назначения.

Workspace config — .repowise-workspace.yaml:

```yaml
version: 1
default_repo: primary
repos:
  - path: /path/to/primary
    alias: primary
    is_primary: true
  - path: /path/to/secondary
    alias: secondary
```

Root/aliases/default и shared environment утверждает пользователь. Для существующего workspace готовый здоровый индекс регистрировать через workspace add /path/to/repo --alias <ALIAS> --no-index; default add запускает indexing. Не повторять init готового индекса.

Workspace MCP читает root .repowise/.env, не каждый дочерний .env. Проверить совместимость embedder/model всех aliases до подключения, не копировать secrets без разрешения. Регистрация не разрешает migration/генерацию.

Проверки: workspace list <ROOT>, полный doctor <ROOT> --workspace --format json; после reload MCP list_repos должен показать exact root/default/all aliases, затем по read-only запросу каждого alias. workspace diagnostics — информация о связях, не замена health.

## 6. Worktree и переписанная история

В 0.59 seeding связано с healthy base checkout, определяемым через Git common-dir. Init сохраняет проверку ancestry seed commit. Но auto-seeding незаполненного linked worktree через update допускает diverged history (require_ancestor=False), если stored commit доступен в target; затем выполняется catch-up. Поэтому отсутствие ancestry не означает невозможность любого поддерживаемого seed-маршрута. Проверить конкретную команду, candidate и runtime. --no-seed для init сознательно выбирает cold init. Не копировать .repowise вручную и не запускать update только ради seeding без разрешения на эту мутацию.

Если worktree уже имеет собственный совместимый индекс, обновлять его. Для soft reset/squash/rebase сначала выбрать существующий стабильный base в этой истории, затем inspect dry-run:

```bash
repowise update /path/to/repository --no-workspace --no-agents \
  --index-only --since <BASE_COMMIT> --dry-run
```

После проверки диапазона и разрешения повторить без --dry-run. Сам skill не разрешает soft reset/rebase. Не угадывать base по другой задаче/checkout. При несовместимом inherited state сначала диагностировать, затем отдельно согласовать recoverable move/rebuild, без автоматического удаления или init --force. Готовые ветки сохранены в Recipes 9–10 основного skill.

## 7. Update и model-written prose

Обычный update синхронизирует структуру/Git/health/file pages. Он не доказывает обновления существующей concept prose; docs-enabled путь может использовать provider для вспомогательной работы. --index-only исключает documentation provider work, но embeddings остаются отдельным механизмом.

--working-tree явно добавляет uncommitted staged/unstaged/untracked inputs. Совпадение marker HEAD само по себе не доказывает, что dirty content не был прочитан. Без разрешения этот режим не добавлять.

--docs не заменяет generate. --full поднимает один fast index до полного: сначала --full --dry-run, затем одобренная мутация. Это не full-project refresh уже написанной prose. При workspace --full требует один --repo.

Выбор model generation:

- semantic claims одной подсистемы устарели — generate --path <PREFIX> --cascade full;
- известны exact IDs — repeatable --page <ID> --cascade full;
- ещё template/unwritten — --unwritten --cascade none;
- явно нужен полный refresh — --all;
- меняется стиль — restyle <STYLE>, без dry-run.

Добавлять только согласованные provider/model/reasoning/concurrency. Все generate сначала --dry-run; сохранить exact planned IDs и cascade dependents, показать scope/cost, после одобрения повторить без dry-run с UTC boundary. Cascade expansion — не автоматическое разрешение на чужие подсистемы. restyle подтверждать по фактическим prompt; same-style cleanup тоже требует явной цели.

При interruption идентичный restyle использует checkpointed persistence; при stale/contamination/неизвестном failure не повторять команду вслепую.

## 8. Acceptance, accounting и contamination

Полный doctor --format json (не --quick) проверяет нужные stores/MCP. --quick сознательно пропускает запуск MCP и reconciliation vector/FTS. Проверять structured status/details каждого нужного check, exit code, пропущенные проверки. JSON выходит 1 при failed check; warn не равен fail. Optional/version warning классифицировать отдельно, не скрывать и не запускать repair автоматически. Старое All checks passed! не является универсальным парсером 0.59.

Требуемые критерии установить для операции: exact sync HEAD, eligible SQL/vector/FTS sets и drift, stale state, docs pointer/prose preservation или scope-written output, фактический MCP smoke при наличии регистрации. Raw wiki_pages count не равен eligible search set; excluded/below-floor/tombstone строки не должны провоцировать лишний reindex.

В 0.59 Coordinator считает все SQL-страницы, включая tombstones. После правильного удаления их векторов его raw drift может остаться ненулевым; это не опровергает доказанное точное совпадение eligible ID sets. Сообщить буквальный WARN/FAIL отдельно и объяснить популяции, не удалять SQL-историю и не перестраивать здоровый vector store ради нулевого счётчика. Равные raw counts тоже не доказывают равенства ID sets.

Для structural-only результата требуется отсутствие нерешённых stale structural pages в согласованном repair scope, не глобальный ноль stale pages. Сохранённую stale model-written concept prose перечислить отдельно без регенерации: её наличие не разрешает generate и не превращает успешный structural refresh в незавершённый structural repair. Все doctor warnings/failures по-прежнему разобрать и сообщить; такой результат не означает полностью чистую wiki или безусловный PASS всего doctor.

Если выбраны pages старого renderer, отдельно подтвердить актуальность их metadata.render_key относительно текущего renderer и сохранённых indexed subject hashes. Freshness=fresh, совпавший глобальный fingerprint и старые timestamps не доказывают исполнения выбранного refresh. Pinned fork передаёт эту работу в structural repair и проверяет текущий подписанный parse cache перед idle-выходом, не читая source-only WIP. Диагностика отсутствующего, повреждённого, слишком большого или небезопасного кеша означает неизвестный результат проверки, не PASS. При несовпадении ключей сначала read-only диагноз; не продвигать markers вручную, не менять docs_mode и не запускать generate/reindex. После исправления причины и согласования recovery scope используется тот же Recipe 1A с --index-only.

Для generate/restyle exact .repowise/jobs/<ID>.json — основной execution record. Выбирать checkpoint по emitted ID либо repo/provider/model/UTC/plan, а не только по newest. SQL generation_jobs может описывать другой cli_update.

Invariant: planned = completed + failed + skipped. Сверять exact IDs, disjoint sets, counters и skip_reasons. Native written/unchanged/retired сохранять отдельно; completed включает reused/unchanged. Written требует current-run persistence; unchanged — current native outcome и совпадение pre-run content/hash. Старый timestamp или metadata_json.reused_from_prior_run от давнего run сами по себе недостаточны.

После model work выполнить основной skill accounting-скрипт и schema-aware mode=ro SQLite audit content и optional digest. Marker scan — поиск кандидатов, не доказательство полной чистоты; проверить approved written/reused scope. Digest-only leaked commentary тоже contamination. Ranked search не гарантирует все SQL matches. Патч final-only Codex не очищает старые записи автоматически.

Не выводить успех из Generating pages, общего page count, cumulative tokens, $0.00, exit zero или checkpoint completed без accounting. При полном prose результате проверить --unwritten --cascade none --dry-run: stubs не должны оставаться; для targeted scope глобальный ноль не требовать.

Partial result останавливает новые мутации, но не read-only diagnosis: сохранить исходную команду/output/exit/plan/checkpoint/UTC; проверить SQL rows/versions, content/digest, status и full doctor на согласованном runtime. Skipped_no_file_contexts требует причины/context fix, не идентичного retry. Не называть silent drop «приблизительной оценкой» без доказательства.

## 9. Vector repair и продолжение

Reindex не пишет prose, но пишет embeddings и может вызвать внешний API. Это отдельное разрешение. Не запускать его после каждого successful update и не ремонтировать raw-count разницу при совпадающих eligible sets.

При diagnosed missing vectors с тем же embedder/model можно согласовать reindex . --embedder <EMBEDDER>. Если явно доказана memory/timeout проблема, меньший --batch-size допустим после классификации причины, не бесконечный retry.

Если все orphan IDs — SQL template file_page tombstones и их target отсутствует одновременно в живом дереве (включая symlinks), HEAD и Git index, применим точечный Recipe 11C без reindex. Нужны отдельное разрешение на exact IDs, остановленные writers/MCP и preview receipt проверенного helper из scripts/cleanup_tombstone_vectors.py. Apply повторно проверяет root/HEAD/полный vector-ID fingerprint и весь допустимый набор, затем удаляет только утверждённые векторы. Никаких SQL/source/prose/state изменений или embeddings; после операции — точное равенство оставшихся IDs и полный doctor/preservation audit. Смешанный набор, отсутствующая SQL-строка, model-written/другой тип страницы, существующий файл или изменённые inputs блокируют этот рецепт. Одобрение одного набора не распространяется автоматически на другие repo.

Для остальных diagnosed orphaned/damaged store либо утверждённой смены embedder/model отдельно согласовать recoverable vector-store backup вне repo и clean reindex (Recipe 11B). Не двигать healthy store автоматически. До удаления/перемещения проверить exact path, ownership, active use и recovery need. Сохранить backup до eligible-set/semantic/full doctor acceptance. При failed rebuild оставить оба каталога и сообщить точное состояние.

Doctor --repair может выполнять другие действия; не использовать его вместо диагностики. После завершения согласованных критериев остановиться; повторный аудит и дополнительные repair/generation не являются частью обычного обслуживания.

## Источники текущей проверки

- Working checkout v0.59.0 help перечисленных команд.
- init_cmd/_plan.py и cli/ui/plan_screen — текущие interactive actions.
- cli/worktree и init_cmd/_seed.py — validation и delegation seeding.
- doctor JSON/reporting — structured checks, quick exclusions.
- Code pin проверен регрессионными тестами, Ruff и сборкой четырёх пакетов; synthetic 0.55→0.59 сохраняет prose/state, wheel preview не вызывает provider, MCP stdout содержит только JSON-RPC. Полный suite и последующие исправленные owner-модули проверены; шесть оставшихся macOS/xdist-сбоев воспроизведены на официальном v0.59.0 (Claude Desktop path, два terminal-layout, Distill temp-path и два watch tests). Это не безусловный зелёный полный suite и не live-index acceptance.
