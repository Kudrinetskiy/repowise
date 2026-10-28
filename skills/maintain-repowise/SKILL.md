---
name: maintain-repowise
description: Use when the user explicitly asks to inspect, install, connect, configure, or maintain RepoWise, including single-repo and multi-repo workspace setup, ordinary commits, rewritten Git history, worktree divergence, structural refreshes, and model-written wiki generation.
---

# Maintain RepoWise

Select one complete recipe from the observable repository state and requested result. Do not assemble a new workflow from fragments when a matching recipe exists.

For installation, initial configuration, MCP/Ollama setup, local excludes, upgrades, and the human-facing daily workflow, read [references/repowise-installation-and-usage.md](references/repowise-installation-and-usage.md). Load that reference only when the request reaches those topics; the recipes below remain the operational command source.

Installing or upgrading the global RepoWise CLI is user-controlled. Never do it because a warning advertises a newer version, and never do it as an implicit maintenance step. Execute the pinned upgrade only when the user explicitly asks the agent to upgrade, or give the documented command when the user explicitly chooses to run it personally.

## Resolve placeholders first

- `<REPO_ROOT>`: exact repository or worktree root.
- `<WORKSPACE_ROOT>`: exact directory containing the approved `.repowise-workspace.yaml`; it may be a neutral directory outside every repository.
- `<REPO_ALIAS>`: exact alias from `.repowise-workspace.yaml` or `repowise workspace list <WORKSPACE_ROOT>`.
- `<BASE_COMMIT>`: existing stable commit immediately before a rewritten range in this repository.
- `<WORKTREE_BASE_COMMIT>`: existing commit in the current worktree's own history.
- `<PATH_PREFIX_1>` and `<PATH_PREFIX_2>`: repository-relative feature directories. Remove the second `--path` line when only one is needed.
- `<PAGE_ID_1>` and `<PAGE_ID_2>`: exact IDs from `wiki_pages.id` or RepoWise page output, such as `module_page:src/api`; repeat `--page` for every approved page.
- `<MISSING_PAGE_ID>`: one planned concept page that was not proven persisted; resolve it from the approved dry-run plan.
- `<JOB_JSON>`: exact `.repowise/jobs/<job-id>.json` checkpoint for the real `generate` or `restyle` run being diagnosed. Resolve it from the emitted job ID/path or by matching the UTC boundary, repository, provider, model, and plan; never select a file only because it is newest.
- `<PLANNED_PAGE_IDS_FILE>`: preserved approved dry-run page IDs, one exact ID per line. If RepoWise printed only counts, record that exact identity comparison is unavailable instead of inventing IDs.
- `<PROVIDER>`, `<MODEL>`, `<REASONING>`, `<CONCURRENCY>`: values from this repository's `.repowise/config.yaml`, `repowise status`, or explicit user direction.
- `<EMBEDDER>`: configured semantic embedder (`ollama`, `gemini`, `openai`, `openrouter`, `edenai`, or `mock`); resolve it from `.repowise/config.yaml` and the available credentials/models. For auto-resolution omit init's `--embedder`; only commands whose current help accepts `auto` (such as reindex) may receive that literal value.
- `<STYLE>`: `comprehensive`, `caveman`, `reference`, or `tutorial`.
- `<BACKUP_PATH>`: explicit backup destination outside `<REPO_ROOT>`.
- `<VECTOR_BACKUP_PATH>`: explicit backup destination for the current `.repowise/lancedb`, outside `<REPO_ROOT>` and not already present.
- `<RUNTIME_PYTHON>`: verified Python interpreter of the approved RepoWise installation, with its dependencies; do not assume the system `python3` has them.
- `<SKILL_ROOT>`: absolute path to this installed skill directory.
- `<CLEANUP_RECEIPT>`: approved evidence-file path outside the target repository for the vector-only cleanup preview; it contains IDs and verification metadata, not index contents.

Never paste unresolved placeholders. Target: patched `0.59.0` at `3cd7acb0c485f9275bcf8f53b9c388fe9f80d6e3`. This runtime pin names the tested CLI code commit; `main` may additionally contain separately validated skill, helper and documentation changes that do not change the installed CLI. This document establishes no installed version or live-index state. Inspect the actual runtime/help. Installation, first new-runtime index access, MCP changes, reindex, and LLM work require applicable authorization; inspection alone grants none.

### Target 0.59 contracts

Options were checked against the working patched 0.59 CLI. Establish acceptance for the final pin and actual indexes separately; historical test counts are not current proof. Preserve user-selected provider/model/reasoning rather than selecting a model from an example.

- Preserve native CLI `written`, `unchanged`, and `retired` outcomes. JSON checkpoint `completed_page_ids` includes reused/unchanged pages; `failed` and `skipped` remain separate. Do not invent checkpoint `written_page_ids` or subtract unchanged pages from completed.
- A written page requires current-run persistence evidence. An unchanged page can retain its old timestamp: require its exact planned ID, native unchanged outcome, and prior stored content/hash identity. Match all planned IDs to outcomes; retired IDs must be separately explained and cannot silently disappear from an approved plan. Complete refresh does not mean every row was rewritten.
- In 0.59, persisted `metadata_json.reused_from_prior_run` identifies reused rows. Read it with `json_extract(metadata_json, '$.reused_from_prior_run')`, then reconcile those exact IDs with the current checkpoint/native report and the pre-run content/hash snapshot. A marker left by an older run is not sufficient by itself.
- Audit stored `content` and optional `digest` using schema-aware read-only SQLite, without opening an old index through the new CLI. A clean content field does not clear contaminated digest text.
- Compare eligible SQL search IDs with vector/FTS IDs, not raw `wiki_pages` counts. Intentional excluded/below-floor rows are not missing vectors; do not repair them when eligible sets are synchronized and drift is zero.
- Dry-run is a logical model/wiki/state no-write preview, not filesystem immutability. It may touch metadata, caches, locks, episodes and WAL/SHM; first new-runtime access may migrate schema. Establish the approved preservation/backup policy and the upgrade reference's old-process isolation gate before opening old indexes with a new runtime, including status, doctor, preview or MCP.
- Normal `update` and `update --docs` still do not refresh existing concept prose. `generate` remains per concrete repository, not workspace-wide, and does not accept `--no-agents`. Saved Ollama embedder selection, actual doctor MCP subprocess smoke, automatic health rescore, and recursive `**` health rules remain applicable.

`init` and `update` recipes always use `--no-agents`. `generate` and `restyle` do not support that flag and do not manage `AGENTS.md`. Current init may save the authenticated API key by default; for ephemeral credentials use explicitly approved `--no-save-key` / `REPOWISE_NO_SAVE_KEY=1` rather than silently persisting secrets. `--no-editor-setup` also skips post-commit hook installation.

## Inspect before proposing installation

Never answer an installation request with a generic `init` block. Inspect the target first, using read-only commands, and report what is already present before offering any mutation:

```bash
cd <REPO_ROOT>
git rev-parse --show-toplevel
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

If `.repowise/.env` exists, inspect only the embedder selector/model and the names—not values—of API-key variables. Report the embedder that RepoWise is likely to auto-detect; never print secrets.

Then classify the observed state:

| State | Required action |
|---|---|
| `state.json`, database, and config exist | Run read-only `repowise status` and full `repowise doctor`. If healthy, do **not** reinstall; choose an update/generate recipe from the actual sync state. |
| `.repowise/` exists but a complete state does not | Inspect its files and any resume/checkpoint evidence. Do not infer installation and do not delete it; report whether it is empty MCP scaffolding, a partial init, or an unknown artifact. |
| Existing index errors after a CLI upgrade | Diagnose schema/migration compatibility and preserve a backup. Do not hide the error with a fresh `init`. |
| No RepoWise index exists | Report the verified absence, then ask the user to choose the installation interaction and wiki mode described in Recipe 8. |

Record whether `.claude/`, `.vscode/`, `.codex/`, `.mcp.json`, and `AGENTS.md` already existed. Later verification must distinguish pre-existing user files from files created by RepoWise. Do not ask the user to run checks the agent can safely run itself. Do not run `doctor --repair`, delete `.repowise`, rewrite editor settings, register MCP, or install/upgrade the CLI without the user's applicable request or approval.

## Determine single-repo or workspace mode from current state

Do this before choosing any `init`, `update`, MCP-registration, or maintenance recipe. Never add `--no-workspace` by habit.

1. Resolve every repository path that the user actually placed in scope and run the inspection above in each one. For an existing index, compare `repowise status` with `git rev-parse HEAD` and run the full `repowise doctor`.
2. Inspect `codex mcp list`. If its RepoWise command names a path, treat that path only as a candidate MCP root and inspect it; do not assume it is current or healthy.
3. Inspect `.repowise-workspace.yaml` only at a workspace root explicitly named by the user, named by the current MCP command, or already established by the current task. Do not scan arbitrary parent directories or derive a workspace from ChatGPT/Codex attached folders.
4. Inspect each repo's `.repowise/config.yaml`, `.repowise/state.json`, and only non-secret embedder/provider variable names. If a workspace is intended, also inspect `<WORKSPACE_ROOT>/.repowise/.env` without printing secret values.
5. Classify the operation with this table before rendering a command:

| Observed state and requested scope | Mode |
|---|---|
| No workspace config is in scope and exactly one repository is targeted | Single-repo: use `<REPO_ROOT>` plus `--no-workspace`. |
| A valid workspace config is in scope and every configured repo should be synchronized | Workspace-wide: use `<WORKSPACE_ROOT>` plus `--workspace`. |
| A valid workspace config is in scope and one configured repo should be synchronized | Workspace-selected: use `<WORKSPACE_ROOT>` plus `--repo <REPO_ALIAS>`. |
| Several healthy indexes exist but no approved workspace config exists | Keep them independent, or obtain approval and use Recipe 12 to register them without re-running `init`. |
| Several folders are attached to one ChatGPT/Codex project | No RepoWise conclusion. Attached folders neither create nor select a RepoWise workspace. |
| Concept prose must be generated | Select one concrete repository path and use `generate` there. RepoWise 0.59 has no workspace-wide concept-generation command. |

The literal `--no-workspace` blocks in Recipes 1-10 are single-repository branches. Use them only after this gate selects single-repo mode. For structural synchronization inside an approved workspace, use Recipe 12's `--workspace` or `--repo` branches. History-rewrite recipes remain scoped to one concrete Git history; if the repo is registered in a workspace, either use `update <WORKSPACE_ROOT> --repo <REPO_ALIAS>` when the required options are supported together, or intentionally force the concrete repo with `--no-workspace` and state that the operation is single-repo maintenance.

One RepoWise workspace MCP process loads runtime environment from `<WORKSPACE_ROOT>/.repowise/.env`, not from every child repository's `.repowise/.env`. Before repointing MCP, prove that all registered indexes use a compatible embedder and embedding model. Do not silently combine indexes built with different embedding models. Changing an embedder/model is a separate approved clean reindex under Recipe 11.

## Why dry-run is required

Use `--dry-run` before commands whose selected scope can be expensive or wrong:

- For `update --since`, verify the commit range, changed files, and planned structural pages before RepoWise changes its stored sync state. The preview does not persist graph, page, or state changes.
- Logical dry-run guarantees do not imply byte-for-byte immutability of .repowise. Establish preservation before preview; cache hashes do not prove wiki/state persistence.
- For `generate --path` and `generate --all`, verify the model page plan, cascade scope, provider/model, and estimated cost before any LLM call or page persistence.
- Preserve the approved dry-run total and every displayed page ID/dependent as run evidence. They are needed to identify a page that the real checkpoint leaves unaccounted.
- Treat a correct dry-run as approval of selection and cost, not proof that runtime file contexts can be built or that the real command succeeded. A page may be selected by dry-run and then skipped before its generation coroutine is created. Run the recipe's checkpoint, persistence, contamination, `status`, and `doctor` checks after execution.

In the pinned patched build, dry-run planning, scope resolution, cost estimation, and real generation share the same near-clone-deduplicated selection. `generate --all` contains only current generatable concept IDs; retired or obsolete stored IDs are excluded. Other scopes are intersected with the same current selection, and an explicitly requested retired ID is reported rather than silently planned. This removes planner-only pages, but it does not eliminate legitimate runtime skips such as onboarding gates or missing file contexts.

### Logical dry-run guarantees

`update --full --dry-run` previews a single repository's fast-to-full upgrade without model generation or wiki/state persistence. Metadata, caches and WAL/SHM may change; establish the preservation policy before first new-runtime access.

`update --full` is not a universal concept-prose refresh. It upgrades one repository from the fast/indexed tier to the full tier and fills page families that are missing; it does not replace `generate --path`, `generate --page`, or `generate --all` for already-written concept prose. To upgrade a fresh `No prose` index, normally use `generate --unwritten --cascade none`. When the requested result is a full concept-prose refresh, preview and run the matching `generate --all` recipe instead.

`init --dry-run` can create recoverable ingestion/session caches inside .repowise. It is not filesystem-read-only; record preflight and preservation policy first.

Routine `update` without `--since` does not require a preview when the goal is ordinary structural synchronization. In the patched runtime, plain `update` does not refresh existing concept prose; use an explicit `generate` recipe for that result. Use `--index-only` when the run must avoid all provider-dependent work. `restyle` has no dry-run, so its interactive confirmations are the scope and cost gate.

## Choose the update mode

- Plain `repowise update` is the ordinary graph, Git, health, index, `symbol_spotlight`, and `file_page` synchronization. In the patched runtime, even an `llm` repository uses the file-page update path; it does **not** regenerate existing concept prose. The docs-enabled branch may still call the configured provider for decision extraction or session mining, so plain `update` is not a no-LLM guarantee.
- `--index-only` explicitly forces the structural path with no provider or LLM work. Use it when model-written prose is out of scope or a following `generate --path`, `generate --page`, or `generate --all` command owns the model work.
- `--docs` overrides a persisted `deterministic` / `no-prose` mode for one incremental run, but the patched runtime retain the file-page update path. It does not rewrite concept prose and does not replace `generate --path`, `generate --page`, `generate --all`, or `generate --unwritten`.

Do not infer LLM concept generation from `Generating pages`, `Pages updated`, generation-job totals, cumulative `Total tokens`, or `$0.00` cost. Those counters mix structural rendering and other pipeline work.

## Decide whether model-written prose is stale

Ask: **Could the old model-written page cause an agent to make a wrong architectural, product-behavior, or operational decision?** If yes, refresh the affected prose. File count and commit count are not decision criteria.

Use targeted `generate --path` when a change alters any of these claims:

- module purpose or responsibility;
- user workflow, business rule, or state contract;
- architecture boundary, data flow, navigation, or lifecycle;
- public API, external contract, or subsystem interaction;
- onboarding, build, startup, or material ADR/README/specification guidance;
- subsystem composition through a conceptually significant addition, removal, or move;
- page truth because the existing prose is stale, incorrect, or contaminated.

Keep model generation out of scope for formatting, tests of existing behavior, an implementation-only bug fix that preserves contracts, internal refactoring, private renames, generated files, or localization that does not alter the workflow.

Select the generation scope from the observed condition:

| Condition | Command family |
|---|---|
| One feature or subsystem changed semantically | `generate --path ... --cascade full` |
| Concept pages are still template/unwritten | `generate --unwritten --cascade none` |
| Cross-cutting architecture changed across most subsystems | `generate --all` |
| Confirmed contamination affects the wiki broadly | `generate --all` or `restyle`, according to whether style must change |
| Only structural/code facts changed | No separate `generate`; use the appropriate `update` recipe |

Do not escalate from targeted generation to `--all` merely because a history rewrite or a large commit range touched many files. Require a full-project semantic reason.

## Prove model-written persistence

Before every real `generate` or `restyle`, capture a UTC boundary:

```bash
REPOWISE_GENERATION_STARTED_AT="$(date -u '+%Y-%m-%d %H:%M:%S')"
```

After the command, query the persisted concept rows directly:

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

Match the returned IDs/types against the dry-run plan and real command result. This timestamp query proves only newly written rows: separately account for native unchanged outcomes using exact planned IDs and prior stored content/hash identity. An older timestamp for a proven unchanged page is not a persistence failure. A plain `update` is expected to return no refreshed existing concept rows.

For a known contaminated set, prefer repeatable `--page <page-id>` over a broad path prefix. Always dry-run with `--cascade full`; if another cascade reports dependent pages that will become stale, do not use it unless a separate recovery for those pages is part of the approved scope.

## Prove generation checkpoint accounting

After every real `generate`—and after `restyle` when that command emits a file checkpoint—inspect the exact file checkpoint under `.repowise/jobs/` before interpreting SQL `generation_jobs`. Treat the JSON checkpoint as the primary execution record: the newest SQL row can belong to an unrelated structural `cli_update`.

Run this read-only check with the exact checkpoint and the preserved approved plan. Pass `-` instead of `<PLANNED_PAGE_IDS_FILE>` only when dry-run exposed counts but not exact IDs:

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
completed_count = int(job.get("completed_pages", len(completed)))
failed_count = int(job.get("failed_pages", len(failed)))
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
    or skipped_count != len(skipped)
    or bool(completed & failed or completed & skipped or failed & skipped)
)
print(f"accounting={'PARTIAL' if partial else 'COMPLETE'}")
PY
```

The required invariant is `planned = completed + failed + skipped`. The pinned build writes `skipped_pages`, `skipped_page_ids`, and per-page `skip_reasons` to the JSON checkpoint and reconciles every planned ID before completion. Treat `unaccounted_count > 0`, an ID in `unaccounted:`, or inconsistent counters/ID lists as a regression and partial result even when exit code is zero, status is `completed`, and `failed_pages = 0`. Legacy checkpoints without skipped IDs still require comparison with the saved dry-run plan. Classify a skip by the recorded reason; do not infer `no_file_contexts` from a count mismatch alone.

SQL `generation_jobs` is supplemental. Use `json_extract(config_json, '$.source')` and timestamps to prove that a row belongs to the same command; if it is absent or says `cli_update`, it cannot override the JSON checkpoint for a real `generate`.

## Stop mutations, not diagnostics

A nonzero exit, unexplained persisted-page count mismatch, missing/extra planned ID, `failed_pages > 0`, unresolved in-scope stale/degraded result, or confirmed contamination is a partial result. Preserved stale concept prose outside an approved structural-only scope must be reported separately; it is not an unresolved structural repair or permission to generate prose. In 0.59, written plus proven unchanged outcomes explain a smaller timestamp-selected row set; unchanged is not skipped or failed. Fail closed on **new mutations only**.

Read-only postchecks are mandatory and do not require new approval:

- preserve the original command, stdout/stderr, UTC boundary, dry-run plan, and exit code;
- run **Prove generation checkpoint accounting** against the exact `.repowise/jobs/*.json` file;
- run **Prove model-written persistence** and **Audit model-written pages** for the completed scope;
- run `repowise status` and full `repowise doctor` without `--repair`;
- use Recipe 2B to inspect the missing/current row, version history, exact file checkpoint, and only then any matching supplemental SQL generation job;
- classify the result as planner estimate/skip, provider/generator failure, checkpoint/persistence failure, timestamp-boundary issue, or still unknown.

Do not run another `generate`, `restyle`, `update`, `reindex`, hook, or repair command until the read-only diagnosis is complete and the new dry-run scope is explicitly approved. If the checkpoint shows `skipped_no_file_contexts` or an inferred unaccounted page consistent with that build-time skip, do not repeat the identical `generate`: dry-run does not prove runtime file contexts, so the same selection is likely to skip again until the selection/context cause is fixed or a working bypass is demonstrated. A partial result is not permission to retry, but it is never a reason to skip diagnostics.

## Interpret status and doctor literally

- `Last sync commit = HEAD`, `0 stale`, and `Drift=0.0%` prove their individual checks only.
- When an update selects older-renderer pages, verify those structural pages' stored `metadata.render_key` against the current renderer and their indexed subject hashes. A global renderer fingerprint, unchanged timestamps or `freshness_status=fresh` do not establish that selected work ran. The pinned fork carries these paths into structural repair and checks the current authenticated parse cache before an idle exit, without reading source-only WIP. Missing, corrupt, oversized or unsafe-cache diagnostics mean the check is unverified, not successful. On a mismatch, stop mutations and diagnose the repair route; do not force markers, change docs mode, generate prose or reindex. After the cause is fixed and the recovery scope approved, Recipe 1A remains the no-model recovery command.
- RepoWise 0.59's coordinator counter counts all SQL pages, including tombstones, rather than the eligible search population. Its raw drift can therefore remain nonzero after a correct tombstone-vector cleanup. Report that literal check separately and prove exact eligible SQL/vector/FTS ID consistency; never delete SQL history or rebuild healthy vectors merely to force the raw counter to zero. A zero raw count drift can also hide equal-sized but different ID sets.
- Exit code zero does not prove that all doctor checks passed.
- Use current full `doctor --format json`: inspect every structured check status/details and preserve exit code. Warnings and failures are distinct; classify each warning. Old table phrases such as `All checks passed!` are not a universal parser.
- `doctor --quick` skips MCP smoke and vector/FTS reconciliation; it cannot close those criteria. Full JSON exits 1 for failed checks; a warning is not automatically a failure or permission to repair.
- A command-specific result may still be proven successful when the only remaining doctor issue is an unrelated optional/version warning, but report that qualification and never say that `doctor` itself passed completely.
- Cumulative `Total tokens` in `status` does not prove that the latest command called the model.
- RepoWise 0.59 `doctor` includes a real MCP subprocess smoke check. When an MCP registration exists, require `MCP server responds = OK`; `not registered - nothing to launch` is an explicit skipped condition, not proof that a configured server works. A missing registered path or invalid JSON-RPC stdout is a real failure.

For structural-only acceptance, require no unresolved stale structural pages in the approved repair scope. Separately identify and report preserved stale model-written concept pages; do not rewrite them, require a global zero-stale count, or infer permission for `generate`. Check every full doctor result and qualify any remaining warning; a structural success does not mean the whole wiki or doctor is completely clean.

RepoWise 0.59 automatically re-scores health on the next `update` when health configuration changes. Do not add a manual repair step. In `health-rules.json`, a pattern ending in `*` matches one path segment; use `**` when the rule must cover a recursive subtree, then verify the affected file set in the update preview/output.

## Audit model-written pages

After every real `generate` or `restyle` run, inspect the generated page scope and audit stored content plus digest when that column exists before declaring success. This read-only SQLite recipe supports legacy 0.48 without adding the column or invoking a schema-migrating new CLI:

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

Use ranked CLI search as a supplemental inspection, not as proof that every matching SQL row was found:

```bash
repowise search "Сначала проверяю"
repowise search "обязательные инструкции"
repowise search "I am still working"
```

Inspect every matched row/field and distinguish legitimate repository documentation from leaked agent commentary. A digest-only leak is confirmed contamination even when content is clean. The marker scan is a candidate finder, not exhaustive proof of clean output; inspect the approved generated/reused scope directly. For targeted generation, inspect timestamp-selected written rows and proven unchanged rows. For `generate --all` or `restyle`, this audit is mandatory across the resulting model-written wiki. A dry-run validates selection and cost only; it does not call the model and cannot validate output quality. If technical commentary is confirmed, stop further mutations, continue every read-only postcheck, and report the affected page IDs, paths, types, fields and timestamps instead of accepting the generation as successful.

When the intended result is a fully model-written concept layer after `generate --all`, `restyle`, or completion of a `no-prose` upgrade, also verify that no concept stubs remain:

```bash
repowise generate . \
  --unwritten \
  --cascade none \
  --provider <PROVIDER> \
  --model <MODEL> \
  --reasoning <REASONING> \
  --dry-run
```

Require `Nothing to generate for that selection.` A previously observed selection bug can produce a false plan of already-written module pages when `--unwritten` uses its default dependent cascade: structural template pages are selected before the command narrows the plan to model-written types. `--cascade none` isolates the actual unwritten concept pages. Do not require this global no-stub result after a targeted `generate --path`, because unrelated concept stubs may intentionally remain outside that scope.

## Recipe 1: Ordinary update using the persisted mode

**When to use:** After normal commits when RepoWise should perform the repository's configured default update.

**Why:** Omitting `--index-only` and `--docs` runs the repository's configured incremental pipeline. In patched 0.59 this synchronizes structural pages but never proves or performs an existing concept-page prose refresh; the provider may still be used for non-page work.

```bash
cd <REPO_ROOT>
git rev-parse --show-toplevel
git rev-parse HEAD
repowise --version
repowise status

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

repowise status
repowise doctor
git rev-parse HEAD
git status --short -- AGENTS.md
```

Confirm `Last sync commit` equals HEAD, no approved structural repairs remain stale, eligible SQL/vector/FTS ID sets agree, and `AGENTS.md` did not change. Report the raw coordinator check and preserved stale concept prose separately without generating it. Classify the timestamp query by page type; structural rows are not LLM prose. Do not report concept prose as refreshed. Apply the full structured doctor gate above; classify every warn/fail separately.

## Recipe 1A: Explicit structural-only update

**When to use:** After normal commits when retrieval, graph, Git signals, health, file pages, and symbol pages must be current, but LLM prose does not need regeneration.

**Why:** `file_page` and `symbol_spotlight` are structural. `--index-only` updates them without model calls or LLM tokens.

```bash
cd <REPO_ROOT>
git rev-parse --show-toplevel
git rev-parse HEAD
repowise --version
repowise status

repowise update . \
  --no-workspace \
  --no-agents \
  --index-only

repowise status
repowise doctor
git rev-parse HEAD
git status --short -- AGENTS.md
```

Confirm `Last sync commit` equals HEAD, no approved structural repairs remain stale, eligible SQL/vector/FTS ID sets agree, and `AGENTS.md` did not change. Report the raw coordinator check and preserved stale concept prose separately; this recipe does not authorize its generation or require a global zero-stale count.

## Recipe 1B: Single-repository fast-to-full upgrade

**When to use:** One existing repository was initially indexed in a fast/reduced tier and the user explicitly wants RepoWise to re-read the whole repository, backfill the full Git tier, and create page families that are currently missing.

**Why:** In RepoWise 0.59, `update --full` upgrades the existing index in place. It is not workspace-wide and does not refresh already-written concept prose merely because code changed; use a separate `generate` recipe for that. Its dry-run is a logical preview, not filesystem immutability.

```bash
cd <REPO_ROOT>
git rev-parse --show-toplevel
git rev-parse HEAD
repowise status

repowise update . \
  --no-workspace \
  --no-agents \
  --full \
  --dry-run
```

Inspect the Git-tier transition, whole-repository page plan, provider/model, and any cost. After explicit approval, repeat the exact command without `--dry-run`:

```bash
repowise update . \
  --no-workspace \
  --no-agents \
  --full

repowise status
repowise doctor
git rev-parse HEAD
git status --short -- AGENTS.md
```

Require `Last sync commit = HEAD`, no unresolved stale pages in the approved structural scope, synchronized SQL/vector/FTS stores, and `MCP server responds = OK` when MCP is registered. Report preserved stale concept prose separately. Do not claim that existing concept prose was refreshed; query concept-page timestamps and obtain approval for a separate `generate` scope when the semantic staleness test requires it.

## Recipe 2: Ordinary update plus targeted LLM pages

**When to use:** After normal commits for which the staleness test above is true for one feature or subsystem and its model-written module, overview, architecture, or onboarding prose must be refreshed.

**Why:** The first step deliberately uses `--index-only` because the following `generate --path` owns the model work. Scoped generation reads the complete repository view and updates only the selected model-written concepts; `--cascade full` keeps their model-written dependents consistent.

```bash
cd <REPO_ROOT>
git rev-parse HEAD

repowise update . \
  --no-workspace \
  --no-agents \
  --index-only

repowise generate . \
  --path <PATH_PREFIX_1> \
  --path <PATH_PREFIX_2> \
  --cascade full \
  --provider <PROVIDER> \
  --model <MODEL> \
  --reasoning <REASONING> \
  --concurrency <CONCURRENCY> \
  --dry-run

REPOWISE_GENERATION_STARTED_AT="$(date -u '+%Y-%m-%d %H:%M:%S')"

repowise generate . \
  --path <PATH_PREFIX_1> \
  --path <PATH_PREFIX_2> \
  --cascade full \
  --provider <PROVIDER> \
  --model <MODEL> \
  --reasoning <REASONING> \
  --concurrency <CONCURRENCY>

repowise status
repowise doctor
git rev-parse HEAD
git status --short -- AGENTS.md
```

Confirm the dry-run selected the intended model page types and preserve every displayed ID/dependent before executing. Then run **Prove generation checkpoint accounting**, **Prove model-written persistence** using `REPOWISE_GENERATION_STARTED_AT`, and **Audit model-written pages**. Match both checkpoint and persisted concept rows to the approved plan. Do not infer either presence or absence of LLM calls from aggregate page counters or `cost_usd: 0.0`.

## Recipe 2A: Regenerate known concept pages exactly

**When to use:** Exact stale or contaminated concept page IDs are known and a path prefix would select unrelated descendants.

**Why:** Repeatable `--page` gives an auditable selection; `--cascade full` refreshes model-written dependents instead of leaving them stale.

```bash
cd <REPO_ROOT>

repowise generate . \
  --page <PAGE_ID_1> \
  --page <PAGE_ID_2> \
  --cascade full \
  --provider <PROVIDER> \
  --model <MODEL> \
  --reasoning <REASONING> \
  --concurrency <CONCURRENCY> \
  --dry-run

REPOWISE_GENERATION_STARTED_AT="$(date -u '+%Y-%m-%d %H:%M:%S')"

repowise generate . \
  --page <PAGE_ID_1> \
  --page <PAGE_ID_2> \
  --cascade full \
  --provider <PROVIDER> \
  --model <MODEL> \
  --reasoning <REASONING> \
  --concurrency <CONCURRENCY>

repowise status
repowise doctor
```

Confirm the dry-run lists the intended page IDs, preserve the exact approved plan, and explicitly report every dependent added by `--cascade full`. Those dependents are in scope only when dependency-consistent cleanup is already authorized; otherwise stop for approval before the real command. Then run **Prove generation checkpoint accounting**, **Prove model-written persistence**, and **Audit model-written pages**. If the dry-run says dependents will merely be marked stale, stop and correct the cascade before the real command.

If the real persisted set differs from the approved plan, do not stop before verification. Run the read-only Recipe 2B and all global postchecks; stop only subsequent mutations.

## Recipe 2B: Partial generation result — read-only diagnosis

**When to use:** A real `generate` or `restyle` did not prove every planned page (written or, in 0.59, identity-proven unchanged), persisted an unexpected page, reported a failure/degraded result, or left contamination.

**Why:** The exact `.repowise/jobs/*.json` checkpoint is the primary execution record for a real `generate` (and for `restyle` when present); `status`, `doctor` without `--repair`, checkpoint reads, and SQLite reads cannot worsen the partial state. Together they distinguish build-time selection/context skips from provider, checkpoint, SQL/FTS/vector, or content failures before any retry.

```bash
cd <REPO_ROOT>

repowise status
repowise doctor

# Run "Prove generation checkpoint accounting" with:
#   <JOB_JSON> = the exact checkpoint for this real command
#   <PLANNED_PAGE_IDS_FILE> = the preserved approved dry-run IDs, or - when unavailable

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

Do not treat the newest SQL row as the real generation job unless its source/timestamps prove that identity; the file checkpoint can describe `generate` while SQL still shows an unrelated `cli_update`.

Also run **Prove model-written persistence** with the original UTC boundary and **Audit model-written pages** over the whole approved plan. Any explicit `skipped` or inferred `unaccounted` page is a partial result. Prepare a new exact `--page ... --cascade full --dry-run` only when the missing page is confirmed, but remember that this dry-run rechecks selection and cost only. If the cause is missing runtime file contexts, first fix the selection/context cause or demonstrate a different working bypass; do not execute an identical recovery command, and do not execute any new recovery plan without approval.

## Recipe 3: Rewritten history without LLM pages

**When to use:** After soft reset, squash, or rebase when RepoWise must ingest the replacement commit range, but concept prose does not need refreshing.

**Why:** The stored sync commit may describe superseded history. `--since <BASE_COMMIT>` replays the new tree range from a known stable point; `--index-only` avoids a redundant model run.

```bash
cd <REPO_ROOT>
git rev-parse HEAD
git cat-file -e '<BASE_COMMIT>^{commit}'

repowise update . \
  --no-workspace \
  --no-agents \
  --index-only \
  --since <BASE_COMMIT> \
  --dry-run

repowise update . \
  --no-workspace \
  --no-agents \
  --index-only \
  --since <BASE_COMMIT>

repowise status
repowise doctor
git rev-parse HEAD
git status --short -- AGENTS.md
```

Confirm the dry-run range is the intended rewritten range. Do not follow this recipe with `update --docs`.

## Recipe 4: Rewritten history plus targeted LLM pages

**When to use:** After soft reset, squash, or rebase when only specific changed feature areas need new model-written descriptions.

**Why:** The first command repairs index and Git-history state. The separate scoped generation refreshes only relevant concepts from a complete repository view.

```bash
cd <REPO_ROOT>
git rev-parse HEAD
git cat-file -e '<BASE_COMMIT>^{commit}'

repowise update . \
  --no-workspace \
  --no-agents \
  --index-only \
  --since <BASE_COMMIT> \
  --dry-run

repowise update . \
  --no-workspace \
  --no-agents \
  --index-only \
  --since <BASE_COMMIT>

repowise generate . \
  --path <PATH_PREFIX_1> \
  --path <PATH_PREFIX_2> \
  --cascade full \
  --provider <PROVIDER> \
  --model <MODEL> \
  --reasoning <REASONING> \
  --concurrency <CONCURRENCY> \
  --dry-run

REPOWISE_GENERATION_STARTED_AT="$(date -u '+%Y-%m-%d %H:%M:%S')"

repowise generate . \
  --path <PATH_PREFIX_1> \
  --path <PATH_PREFIX_2> \
  --cascade full \
  --provider <PROVIDER> \
  --model <MODEL> \
  --reasoning <REASONING> \
  --concurrency <CONCURRENCY>

repowise status
repowise doctor
git rev-parse HEAD
git status --short -- AGENTS.md
```

Use this instead of Recipe 5 when a full-project rewrite would spend time and tokens on unrelated concepts.

## Recipe 5: Rewritten history plus full-project LLM pages

**When to use:** After soft reset, squash, or rebase when the user explicitly wants every model-written project description regenerated, not merely the structural index repaired.

**Why:** `update --index-only --since` first reconciles the rewritten Git range. `generate --all` then refreshes all model-written concept pages from the complete, current repository view.

```bash
cd <REPO_ROOT>
git rev-parse HEAD
git cat-file -e '<BASE_COMMIT>^{commit}'

repowise update . \
  --no-workspace \
  --no-agents \
  --index-only \
  --since <BASE_COMMIT> \
  --dry-run

repowise update . \
  --no-workspace \
  --no-agents \
  --index-only \
  --since <BASE_COMMIT>

repowise generate . \
  --all \
  --provider <PROVIDER> \
  --model <MODEL> \
  --reasoning <REASONING> \
  --concurrency <CONCURRENCY> \
  --dry-run

REPOWISE_GENERATION_STARTED_AT="$(date -u '+%Y-%m-%d %H:%M:%S')"

repowise generate . \
  --all \
  --provider <PROVIDER> \
  --model <MODEL> \
  --reasoning <REASONING> \
  --concurrency <CONCURRENCY>

repowise status
repowise doctor
git rev-parse HEAD
git status --short -- AGENTS.md
```

A history rewrite alone is not sufficient reason to choose this recipe; require an explicit request for a full LLM-wiki refresh.

## Recipe 6: Full-project LLM refresh without history rewrite

**When to use:** When Git history is normal but every model-written project description must be refreshed while keeping the current wiki style.

**Why:** A routine structural update first makes the index current. `generate --all` rewrites concept prose without performing a style migration.

```bash
cd <REPO_ROOT>
git rev-parse HEAD

repowise update . \
  --no-workspace \
  --no-agents \
  --index-only

repowise generate . \
  --all \
  --provider <PROVIDER> \
  --model <MODEL> \
  --reasoning <REASONING> \
  --concurrency <CONCURRENCY> \
  --dry-run

REPOWISE_GENERATION_STARTED_AT="$(date -u '+%Y-%m-%d %H:%M:%S')"

repowise generate . \
  --all \
  --provider <PROVIDER> \
  --model <MODEL> \
  --reasoning <REASONING> \
  --concurrency <CONCURRENCY>

repowise status
repowise doctor
git rev-parse HEAD
git status --short -- AGENTS.md
```

Use Recipe 7 instead when the style must change or old model-output contamination must be replaced across the whole wiki.

## Recipe 7: Restyle or contamination cleanup

**When to use:** When changing documentation style, or when intentionally regenerating the whole wiki to remove old contaminated model output. Reusing the same style is valid for cleanup.

**Why:** `restyle` reuses the current index and graph but regenerates the entire wiki through the configured model and style pipeline.

```bash
cd <REPO_ROOT>
git rev-parse HEAD

repowise update . \
  --no-workspace \
  --no-agents \
  --index-only

REPOWISE_GENERATION_STARTED_AT="$(date -u '+%Y-%m-%d %H:%M:%S')"

repowise restyle <STYLE> . \
  --provider <PROVIDER> \
  --model <MODEL> \
  --reasoning <REASONING> \
  --concurrency <CONCURRENCY>

repowise status
repowise doctor
git rev-parse HEAD
git status --short -- AGENTS.md
```

`restyle` has no dry-run. Read both confirmation prompts before accepting. When the style is unchanged, approve `Regenerate anyway?` only when cleanup is the explicit goal.

## Recipe 8: New repository or independent worktree cold init

**When to use:** The mandatory installation inspection proved that no complete RepoWise index exists, and a linked worktree has no compatible base that should be reused.

**Choice gate:** After reporting the inspection result, resolve two independent user choices: (1) interaction/wiki mode and (2) embedder policy. Do not default either choice. If the user already made a choice explicitly, do not ask it again.

| Choice | Use when | Result |
|---|---|---|
| Interactive setup | The user wants to review RepoWise's own questions and review the current plan screen. | The wizard owns mode/provider/model/style questions; safety-sensitive editor/hook choices remain pinned by flags. |
| Explicit structural setup | The user wants a reproducible, prompt-free first index with no documentation LLM calls. | Structural wiki; search is full-text or semantic according to the separately selected embedder. Model prose can be added later with Recipe 8A. |
| Explicit model-written setup | The user wants a reproducible full prose init with the provider/model/style fixed in advance. | Structural index plus model-written concept pages; search remains a separate embedder choice. Review the dry-run and cost before the real command. |

Resolve one embedder policy before rendering the final command:

| Embedder policy | Command behavior | Result |
|---|---|---|
| Auto-detect | Omit `--embedder`. | RepoWise uses `REPOWISE_EMBEDDER`, then a detected Gemini/OpenAI/OpenRouter credential, then `OLLAMA_EMBEDDING_MODEL`, otherwise `mock`. In a no-prose init an inferred hosted provider is downgraded to `mock` to avoid hidden spend. |
| Choose in the wizard | Omit `--embedder`; use the current plan screen's `e` advanced-options flow and inspect its search question. | The user sees and chooses the available embedder. |
| Explicit provider | Pass `--embedder <EMBEDDER>`. | Reproducibly pins `ollama`, `gemini`, `openai`, `openrouter`, or another supported value. |
| Deliberate full-text only | Pass `--embedder mock`. | Full-text search works; semantic similarity is intentionally unavailable. |

For an explicit Ollama choice, create `.repowise/.env` only if the user also chose a specific model. `ollama list` alone does not select a model. If no model is pinned, RepoWise uses its Ollama provider default. Never create or overwrite this file for auto-detect, wizard selection, hosted providers, or `mock`.

**Why:** `--no-seed` prevents automatic inheritance from another checkout. RepoWise 0.59 treats explicit `--no-prose` as non-interactive, so it will not ask for an embedder. The editor/project-file safety flags remain fixed, while interaction mode and embedder stay independent user decisions. RepoWise 0.59 also respects the repository's saved embedder when `auto` is used; verify the resolved value after init/update rather than overriding it blindly. In 0.59 init still validates ancestry, while update auto-seeding an unindexed linked worktree permits diverged history when the stored commit exists in the target. Inspect the exact command/candidate; do not infer that every seed route is ancestry-only or start update without authorization.

```bash
cd <REPO_ROOT>
git rev-parse --show-toplevel
git rev-parse HEAD
test ! -e .repowise/state.json
```

If the user explicitly chose Ollama with `mxbai-embed-large:latest`, prepare only that choice:

```bash
mkdir -p .repowise
touch .repowise/.env
chmod 600 .repowise/.env
if grep -q '^OLLAMA_EMBEDDING_MODEL=' .repowise/.env; then
  grep -qxF 'OLLAMA_EMBEDDING_MODEL=mxbai-embed-large:latest' .repowise/.env
else
  printf '%s\n' 'OLLAMA_EMBEDDING_MODEL=mxbai-embed-large:latest' >> .repowise/.env
fi
```

Before the selected init command, set the argument array to the resolved policy. Use exactly one line; do not paste an unresolved placeholder:

```bash
REPOWISE_EMBEDDER_ARGS=()                         # auto-detect or choose in wizard
REPOWISE_EMBEDDER_ARGS=(--embedder ollama)        # explicit Ollama example
REPOWISE_EMBEDDER_ARGS=(--embedder mock)          # deliberate full-text only
```

After the common preflight above, run exactly one user-selected branch with the one selected array definition.

### Interactive setup

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

In the 0.59 plan screen, Enter starts the displayed plan, `m` changes model/documentation selection, `e` edits advanced options and `q` quits. When offered, `s` toggles this-repo-only versus global setup; it is not the settings key. Read the actual prompt and let the user choose. Do not assume the old numbered Everything / No prose / Advanced menu. For embedding choice, inspect the available edit flow or pass an explicitly selected `--embedder`; never assume it is always a standalone prompt.

### Explicit structural setup

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
  --no-editor-setup
```

### Explicit model-written setup

First run the same command with `--dry-run`; after the user approves its scope and cost, run it again with `--yes` instead of `--dry-run`:

```bash
repowise init . \
  --no-workspace \
  --no-seed \
  --prose \
  --provider <PROVIDER> \
  --model <MODEL> \
  --reasoning <REASONING> \
  --wiki-style <STYLE> \
  --concurrency <CONCURRENCY> \
  "${REPOWISE_EMBEDDER_ARGS[@]}" \
  --no-claude-md \
  --no-agents \
  --no-codex \
  --no-distill-hook \
  --no-editor-setup \
  --dry-run
```

Do not leave placeholders unresolved. Do not add `--yes` until the dry-run has been inspected and approved.

After any selected branch:

```bash

repowise status
repowise doctor
grep -n '^embedder:' .repowise/config.yaml
git rev-parse HEAD
git status --short -- AGENTS.md .claude .vscode .codex
```

Require `config.yaml` to show the user-selected or correctly auto-detected embedder, `doctor` to show SQL/vector/FTS consistency, and no newly created project instruction/editor files relative to the recorded preflight. Check for `mxbai-embed-large:latest` only when that exact Ollama model was selected. Current 0.59 `--no-editor-setup` covers machine/project registration and skips the post-commit hook; retain other explicit opt-outs as defense in depth. Never copy `.repowise` from another checkout.

## Recipe 8A: Promote a new `No prose` index to model-written prose

**When to use:** Recipe 8 or another staged installation completed successfully, concept pages are still template/unwritten, and the user now explicitly wants model-written wiki prose.

**Why:** `generate --unwritten --cascade none` writes only template concept pages. It does not repeat ingestion or rewrite already model-written pages. `update --full` is a different single-repository fast-to-full upgrade and does not replace this recipe.

```bash
cd <REPO_ROOT>
git rev-parse HEAD
repowise status

repowise generate . \
  --unwritten \
  --cascade none \
  --provider <PROVIDER> \
  --model <MODEL> \
  --reasoning <REASONING> \
  --concurrency <CONCURRENCY> \
  --dry-run
```

Preserve the approved plan. Immediately before the real command, capture `REPOWISE_GENERATION_STARTED_AT` as described in “Prove model-written persistence”, then repeat the exact command without `--dry-run`.

After the real run, complete the checkpoint-accounting, persisted-row, contamination, `status`, and full `doctor` checks. `generate` does not accept `--no-agents` and does not manage `AGENTS.md`; still verify `git status --short -- AGENTS.md` as a regression guard.

## Recipe 9: Existing worktree index with a valid own-history base

**When to use:** The worktree already has its own compatible RepoWise index, but update must replay from a known `<WORKTREE_BASE_COMMIT>` in this worktree's history. A merge-base with a different checkout is irrelevant.

**Why:** `git diff <WORKTREE_BASE_COMMIT>..HEAD` only requires the chosen commit to exist locally and belong to the intended history; it does not require ancestry with another checkout.

```bash
cd <REPO_ROOT>
git rev-parse HEAD
git cat-file -e '<WORKTREE_BASE_COMMIT>^{commit}'

repowise update . \
  --no-workspace \
  --no-agents \
  --index-only \
  --since <WORKTREE_BASE_COMMIT> \
  --dry-run

repowise update . \
  --no-workspace \
  --no-agents \
  --index-only \
  --since <WORKTREE_BASE_COMMIT>

repowise status
repowise doctor
git rev-parse HEAD
git status --short -- AGENTS.md
```

Do not use this recipe when `.repowise/state.json` came from unrelated history; use Recipe 10.

## Recipe 10: Replace an incompatible inherited worktree index

**When to use:** A worktree contains `.repowise`, but its stored sync state belongs to another or unrelated history and no trustworthy `--since` base exists.

**Why:** Guessing a base can silently preserve incorrect Git and page state. Moving the old index outside the repository provides rollback; a cold `--no-seed` init builds only from the current worktree.

Obtain user approval for the rebuild and resolve `<BACKUP_PATH>` outside `<REPO_ROOT>` before running:

```bash
cd <REPO_ROOT>
git rev-parse HEAD
test -e .repowise/state.json
mv .repowise <BACKUP_PATH>
```

After the recoverable move, present the three Recipe 8 interaction branches and the separate embedder-policy choice. Run exactly the user's selected combination. Every Recipe 8 branch already includes `--no-seed`; do not default to `--no-prose` or Ollama merely because the incompatible index was removed.

Then run Recipe 8's common `status`, full `doctor`, HEAD, and pre-existing-artifact comparison. Keep `<BACKUP_PATH>` until the new index passes verification. Reapply only the required embedder environment from an approved source rather than copying the old database back.

## Recipe 11: Repair semantic vector drift

**When to use:** `repowise doctor` reports genuine eligible-set vector drift, semantic search misses an eligible page present in SQL/FTS, embedding failed during generation, the vector store was lost or damaged, or the configured embedder / embedding model changed. Compare eligible SQL search IDs, not all stored rows: intentional excluded/below-floor rows do not require vectors. If eligible SQL/vector/FTS sets are synchronized with zero drift, a raw-count difference alone requires no reindex or repair.

**Why:** Choose the repair from exact ID sets. `reindex` writes embeddings without calling the documentation LLM or modifying Git; the narrowly guarded Recipe 11C only removes confirmed obsolete vectors without rebuilding. Embedder/model transitions and each destructive cleanup scope require separate applicable authorization.

Run the read-only precheck first:

```bash
cd <REPO_ROOT>
git rev-parse HEAD
repowise status
repowise doctor
```

### 11A: Missing vectors only, same embedder and model

Use ordinary reindex when `doctor` reports missing vectors or an embedding failure, the configured embedder/model is unchanged, and it reports `0 orphaned`:

```bash
cd <REPO_ROOT>

repowise reindex . \
  --embedder <EMBEDDER>

repowise doctor
git rev-parse HEAD
git status --short -- AGENTS.md
```

Require synchronized eligible SQL/Vector sets with `Drift=0.0%`. `reindex` has no dry-run and writes the vector store, so first verify the configured embedder is available. If the first run fails because of memory pressure or an embedding timeout, retry with smaller batches:

```bash
repowise reindex . \
  --embedder <EMBEDDER> \
  --batch-size 8
```

### 11B: Orphaned vectors or embedder/model change — clean reindex

Use a clean reindex for diagnosed orphaned/damaged stores that do not qualify for Recipe 11C, or when intentionally changing the embedder/model (including `mock` to Ollama). A rebuild is not required merely because a strictly proven tombstone vector can be removed by 11C. Obtain explicit approval for the recoverable clean-store rebuild, resolve `<VECTOR_BACKUP_PATH>`, and move the whole vector directory to a recoverable backup before rebuilding:

```bash
cd <REPO_ROOT>
test -d .repowise/lancedb
test ! -e <VECTOR_BACKUP_PATH>
mv .repowise/lancedb <VECTOR_BACKUP_PATH>

repowise reindex . \
  --embedder <EMBEDDER>

repowise doctor
git rev-parse HEAD
git status --short -- AGENTS.md
```

Require synchronized eligible SQL/Vector sets, `0 orphaned`, and `Drift=0.0%`. Keep `<VECTOR_BACKUP_PATH>` until those checks pass. If the clean reindex fails, leave the backup untouched, stop, and report the error before moving or deleting either vector directory.

Do not regenerate model-written pages to repair vector drift. Do not run `doctor --repair` as a substitute: it may perform unrelated repairs. If a smaller-batch retry also fails, stop and report the embedder error; the SQL wiki remains the source for another clean reindex attempt.

### 11C: Exact confirmed tombstone vectors — no reindex

**When to use:** Full doctor reports zero missing vectors and diagnosed orphans, every orphan is backed by a SQL `template` `file_page` tombstone, every target is absent from the live filesystem (including symlinks), Git HEAD and Git index, and the user explicitly approved this exact deletion scope. A count match or `Drift=0.0%` alone does not establish ID consistency.

**Why:** These search entries no longer represent current files. Removing only their exact vector IDs leaves SQL history, model-written prose, live vectors, decisions and settings intact; a full embedding rebuild is unnecessary. This is not generic orphan pruning: absent SQL rows, model-written rows, other page types, mixed orphan sets, present files or changed inputs must be diagnosed separately.

Before preview/apply, quiesce all writers and MCP access to this index through the approved maintenance lifecycle. Capture the applicable source/prose/state preservation evidence. The helper uses read-only SQLite and the existing delete-only vector API; it never calls an embedder, creates a new store, deletes SQL rows or edits project files. The script does not support `--no-agents` because it never writes agent instructions.

```bash
<RUNTIME_PYTHON> <SKILL_ROOT>/scripts/cleanup_tombstone_vectors.py <REPO_ROOT> \
  --preview > <CLEANUP_RECEIPT>
```

Require a successful exit and inspect the complete receipt: canonical root, HEAD, exact candidate IDs and count, and the complete prior vector-ID fingerprint. Match it to the user's approved scope; never approve by count alone. If inputs change, produce a new preview and obtain any needed approval instead of editing the receipt. A zero-candidate result needs no apply.

After approval, apply that exact receipt:

```bash
<RUNTIME_PYTHON> <SKILL_ROOT>/scripts/cleanup_tombstone_vectors.py <REPO_ROOT> \
  --apply <CLEANUP_RECEIPT>

repowise doctor <REPO_ROOT> --format json
```

Apply revalidates the receipt and live eligibility before deleting. Require the resulting vector-ID set to equal the prior set minus only the approved IDs, then full doctor synchronization and unchanged source/WIP, prose/provenance, state/docs pointer and settings. On any failure, stop new mutations and preserve the exact outcome; do not retry blindly, expand the deletion set, reindex or run broad repair. Authorization for one repository's IDs does not automatically authorize cleanup in another repository.

## Recipe 12: Register and operate a multi-repo workspace

**When to use:** Two or more repositories have their own healthy RepoWise indexes and one MCP server must expose them by alias, or an existing RepoWise workspace must update all repos or one named repo.

**Why:** RepoWise 0.59 workspaces are the product-supported multi-repo route. They are independent of ChatGPT/Codex attached folders. Existing healthy indexes can be registered without another `init`.

### 12A: Inspect before creating or changing a workspace

For every proposed repository, resolve its canonical path and verify its existing index first:

```bash
git -C <REPO_ROOT> rev-parse --show-toplevel
git -C <REPO_ROOT> rev-parse HEAD
cd <REPO_ROOT>
repowise status
repowise doctor
grep -n '^embedder:' .repowise/config.yaml
```

Also inspect the current MCP registration and the exact proposed workspace root:

```bash
codex mcp list
test -e <WORKSPACE_ROOT>/.repowise-workspace.yaml && \
  sed -n '1,240p' <WORKSPACE_ROOT>/.repowise-workspace.yaml || \
  echo 'workspace config: absent'
test -e <WORKSPACE_ROOT>/.repowise/.env && \
  sed -E 's/=.*/=<redacted>/' <WORKSPACE_ROOT>/.repowise/.env || \
  echo 'workspace env: absent'
```

Do not continue if a repo is partial/broken, aliases collide, paths are unresolved, or configured embedders/models are incompatible. Never print secret values.

### 12B: Register existing healthy indexes without reinitializing them

After the user approves the exact workspace root, aliases, default repo, and shared runtime configuration, create the standard RepoWise 0.59 config at `<WORKSPACE_ROOT>/.repowise-workspace.yaml`:

```yaml
version: 1
default_repo: <REPO_ALIAS>
repos:
  - path: /absolute/path/to/primary-repo
    alias: <REPO_ALIAS>
    is_primary: true
  - path: /absolute/path/to/another-repo
    alias: another-repo
```

Absolute repo paths are supported and are appropriate when repositories live in unrelated directories or on different volumes. A neutral `<WORKSPACE_ROOT>` is organizational, not required by RepoWise. Do not run `init` again and do not use `workspace add` with its default indexing behavior for already healthy indexes. If a workspace config already exists, run `cd <WORKSPACE_ROOT>` and then `repowise workspace add <ABSOLUTE_REPO_PATH> --alias <REPO_ALIAS> --no-index` to register one additional healthy index after the same checks.

Create or change `<WORKSPACE_ROOT>/.repowise/.env` only for runtime settings the user approved. With `codex_cli`, no API key is needed. For Ollama semantic search, the workspace MCP needs the compatible `OLLAMA_EMBEDDING_MODEL` used by the registered indexes. Never copy hosted-provider secrets blindly from child repos.

Validate the config before changing MCP:

```bash
repowise workspace list <WORKSPACE_ROOT>
repowise doctor <WORKSPACE_ROOT> --workspace
```

Then repoint the one global RepoWise MCP entry after explicit approval:

```bash
codex mcp remove repowise
codex mcp add repowise -- repowise mcp <WORKSPACE_ROOT>
codex mcp list
```

Fully restart ChatGPT/Codex so the old MCP process exits. Through RepoWise MCP, require `list_repos` to report workspace mode, the exact workspace root, the default alias, and every configured alias; then run one read-only query against each alias.

### 12C: Synchronize workspace indexes

All stale configured repositories:

```bash
repowise update <WORKSPACE_ROOT> \
  --workspace \
  --no-agents
```

Guarantee no provider-dependent work:

```bash
repowise update <WORKSPACE_ROOT> \
  --workspace \
  --no-agents \
  --index-only
```

Only one configured alias:

```bash
repowise update <WORKSPACE_ROOT> \
  --repo <REPO_ALIAS> \
  --no-agents
```

Add `--index-only` to the one-alias command when provider work must be excluded. After any real workspace update:

```bash
repowise workspace list <WORKSPACE_ROOT>
repowise doctor <WORKSPACE_ROOT> --workspace
repowise workspace diagnostics <WORKSPACE_ROOT>
```

Require each repo's recorded sync commit to match its actual HEAD, no unresolved stale pages in the approved structural scope, and zero eligible-store drift. Apply the full structured doctor gate and report every remaining warning/failure, including preserved stale concept prose; do not require a global zero-stale count or generate that prose implicitly. `workspace diagnostics` explains cross-repo provider/consumer links; it is not a substitute for per-repo health.

For model-written prose, run Recipe 2, 2A, 2B, 5, 6, or 8A against the selected concrete repository path. Do not expect `update --workspace` or ChatGPT folder attachment to regenerate concept prose across all repositories.

## Common mistakes and stop conditions

- Do not interpret fail-closed as “stop all checks.” After any partial result, finish the mandatory read-only persistence, contamination, status, doctor, version-history, and generation-job diagnostics; block only further mutations.
- Do not treat `repowise update --full` as universal concept regeneration. In RepoWise 0.59 its dry-run is safe, but the real command is a single-repository fast-to-full upgrade; existing concept prose still requires `generate`.
- Do not use SQL `generation_jobs` as the primary record of a real `generate`/`restyle`. Inspect the exact `.repowise/jobs/*.json` checkpoint first; a SQL `cli_update` row may be newer but unrelated.
- Do not accept `status=completed` or exit code zero when checkpoint accounting violates `planned = completed + failed + skipped`. Treat positive or named `unaccounted` pages as implicit skips.
- Do not accept `every page is now written` or an undifferentiated generated count for a partial run. Preserve 0.59 native written/unchanged/retired output and separately reconcile failed/skipped checkpoint outcomes. Completed includes reused pages; require evidence rather than relabelling unchanged as skipped. An unexplained mismatch requires read-only diagnosis.
- Do not repeat an identical generation command after `skipped_no_file_contexts` or a matching unaccounted build-time skip. Dry-run does not prove runtime file contexts; correct or bypass the context-selection cause first.
- Do not report that plain RepoWise 0.59 `update` refreshed concept prose. Its page generation is `file_pages_only=True`; use explicit `generate` and prove persisted concept rows by timestamp.
- Do not treat `repowise update --docs` as a full concept-wiki rewrite. It overrides a persisted `deterministic` / `no-prose` mode for one incremental run; use Recipe 2, 4, 5, or 6 for model-written module, overview, architecture, or onboarding pages.
- Do not choose `generate --all` merely because of soft reset, squash, or rebase. Choose it only when full-project model prose is explicitly required.
- Do not use changed-file or commit count as a proxy for prose staleness. Apply the semantic decision test and choose the narrowest sufficient generation scope.
- Do not infer `<BASE_COMMIT>` from another task, branch, checkout, transcript, or worktree.
- Do not run `doctor --repair` automatically.
- Do not run `reindex` after every successful update or generation; use Recipe 11 only for observed vector drift, embedding failure, vector-store recovery, or an intentional embedder/model change.
- Do not expect `init --no-prose` in RepoWise 0.59 to ask for an embedder. It is a non-interactive path: resolve the user's auto/explicit/mock policy before the run. Pass `--embedder ollama` and create an Ollama model entry only when the user selected them; otherwise preserve and verify the saved auto-selected embedder.
- Current 0.59 `--no-editor-setup` covers machine registration, project editor files and post-commit hooks. Recipes retain explicit `--no-claude-md --no-agents --no-codex --no-distill-hook` as defense in depth; never enable hooks implicitly.
- Do not assume generic orphan pruning. Recipe 11C is only for its independently verified template-file tombstones and approved exact IDs; other diagnosed orphan/damaged-store cases require the separately approved Recipe 11B or another explicit recovery plan.
- Do not treat `cost_usd: 0.0` as proof that Codex CLI was not called; verify generated page types and provider/model output.
- Do not interpret aggregate `Generating pages`, `Pages updated`, job totals, or cumulative token counts as model-page evidence; query newly written `wiki_pages` after the captured UTC boundary and reconcile 0.59 unchanged IDs against prior content/hash and current native outcome evidence.
- Never close store/MCP criteria with `doctor --quick`, selected OK rows, exit zero alone, or a historical final phrase; require current full structured checks.
- Do not expect an external directory to enter a single-repository index. Stop and report the indexing boundary.
- Do not infer a RepoWise workspace from multiple folders attached to a ChatGPT/Codex project. Workspace membership exists only in the approved `.repowise-workspace.yaml`.
- Do not add `--no-workspace` before inspecting actual workspace state and requested scope. In a configured workspace use `--workspace` for all repos or `--repo <REPO_ALIAS>` for one alias; force single-repo mode only intentionally.
- Do not repoint MCP to a workspace until its shared runtime environment and embedder/model compatibility are verified. Workspace MCP does not load every child repo's `.repowise/.env`.
- Stop if a base commit is absent, the installed RepoWise version lacks an option, `doctor` reports unresolved in-scope structural stale/drift/registration failures, or replacing `.repowise` lacks user approval. Preserved stale concept prose must be reported separately and does not authorize expanding structural maintenance into generation.
