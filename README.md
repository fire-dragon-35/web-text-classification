# web-text-classification

Crawls the sources in `config/sources.yaml`, stores pages and their sections in SQLite, and classifies every
stored section against the taxonomy in `config/categories.json` with Claude.

```bash
python -m cli crawl [SOURCES_FILE] [--only ID]... [--db .assets/documents.db] [--verbose]
```

```bash
set -a; . ./.env; set +a
export CLASSIFICATION_MODEL=claude-sonnet-5-5
python -m cli classify [--taxonomy config/categories.json] [--only ID]... [--max-depth 2] [--min-chars 200] [--batch] [--db .assets/documents.db] [--verbose]
```

`SOURCES_FILE` defaults to `config/sources.yaml`. Generated data such as `documents.db` lives in `.assets/`,
which is not tracked by git.

`classify` reads `ANTHROPIC_API_KEY` and `CLASSIFICATION_MODEL` from the environment. A section is
classified once per text, classifier, taxonomy and depth; reruns reuse stored results.

## `--min-chars`

Sections whose text is shorter than `--min-chars` characters (default 200) are not sent to Claude. They are
reported as `skipped` and nothing is stored for them, so a rerun with a lower value classifies them.

## `--batch`

Without `--batch`, sections are classified one request at a time. With `--batch`, all pending sections are
classified through the Message Batches API: one batch per taxonomy level, built from the codes chosen at the
level above. Prompts, cache breakpoints and schemas are the same as without `--batch`.

The open batch and every section's progress are stored in the `pending_classification` table. An
interrupted run (Ctrl-C) resumes by polling the same batch when it is started again with the same
model, taxonomy and `--max-depth`. A classification row is written only when all levels of a section are
done. A section whose request errors, expires, is refused or hits `max_tokens` is reported as `failed` and
is retried on the next run.

## Usage columns

Every classification row stores the tokens of all requests for that section, summed over its levels:

| Column | Meaning |
|---|---|
| `input_tokens` | Input tokens after the cache breakpoint |
| `cache_creation_input_tokens` | Input tokens written to the prompt cache |
| `cache_read_input_tokens` | Input tokens read from the prompt cache |
| `output_tokens` | Output tokens, including thinking |

Rows classified before these columns existed have `NULL` usage. The run summary prints the totals for the
sections classified in that run and the cache hit ratio,
`cache_read / (cache_read + cache_creation + input)`.
