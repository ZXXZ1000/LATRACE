# Lexical Hybrid Code Review Rectification

## Scope

This note captures the review findings for the lexical hybrid search change set and
turns them into an execution-oriented cleanup list.

## Confirmed Findings

1. `lexical_hybrid` config resolution is duplicated in `service.py`.
   - The same YAML + runtime override merge appears in the cache-signature path and
     again in the retrieval path.
   - This is a real DRY issue and should be centralized.

2. `search()` reads cached config more than necessary.
   - The method already loads cached config near the beginning.
   - A later reload for lexical settings is unnecessary and reduces readability.

3. `runtime_overrides.json` is acting as a repo-default override layer.
   - This is intentional from the runtime persistence mechanism, but it also means
     the repo can silently ship behavior that differs from YAML defaults.
   - This is a product/config governance concern, not only a style issue.

4. `runtime_overrides.json` is missing a trailing newline.

5. `InMemVectorStore.fetch_text_corpus()` is order-sensitive.
   - It currently relies on dict insertion order.
   - That makes test behavior less deterministic than it should be.

6. The lexical tokenizer test coverage is still narrow.
   - The current unit test validates the core mixed Chinese/English case.
   - Empty input, punctuation-only input, and number-heavy input should also be covered.

## Outdated Or Partially Accurate Review Points

1. `lexical_hybrid.enabled` is not currently committed as `true`.
   - In the current worktree, `runtime_overrides.json` keeps it as `false`.
   - The actual issue is that repo-tracked overrides can still shadow YAML defaults.

2. The duplicate merge in `server.py` is lower risk than the two in `service.py`.
   - The server-side merge is used for config snapshot display.
   - The main maintainability risk is still the duplicated execution-path logic in
     `service.py`.

## Safe Fixes To Apply Now

1. Centralize lexical hybrid config resolution in a shared helper.
2. Reuse the first cached config load in `MemoryService.search()`.
3. Make in-memory lexical corpus iteration deterministic.
4. Add tokenizer edge-case unit tests.
5. Add the missing trailing newline to `runtime_overrides.json`.

## Changes To Hold For A Separate Decision

1. Clearing repo-tracked `runtime_overrides.json` back to empty defaults.
   - This may change current effective retrieval behavior.
   - It should be handled deliberately, not folded into a code-quality cleanup.

2. Reverting or splitting QA/Judge model changes from the lexical hybrid branch.
   - This is a valid review concern.
   - It is safer to handle as a separate configuration decision or commit split.

## Execution Plan

1. Refactor lexical config resolution into a shared helper.
2. Update `service.py` and config snapshot usage to consume the helper.
3. Make `fetch_text_corpus()` deterministic in the in-memory store.
4. Expand unit tests for tokenizer edge cases.
5. Run targeted lexical hybrid unit tests and config endpoint tests.
