# kata-cli log schema

The local capture log lives under `.antoine/log/` relative to the
current working directory. Two-tier layout:

- `<YYYY-MM-DD>.jsonl` — shape index. One row per captured tool call.
- `args/<session>.jsonl` — raw args sidecar. Privacy-sensitive; deleted
  first by `kata log gc`.

## Shape row (JSONL)

| Field          | Type   | Required | Notes |
|----------------|--------|----------|-------|
| `ts`           | string | yes      | ISO-8601 UTC; the date prefix selects the shard file. |
| `session`      | string | yes      | Adapter-assigned session id; keys the args sidecar. |
| `agent`        | string | yes      | `claude-code`, `codex`, etc. |
| `tool`         | string | yes      | Backend-native tool name (`Bash`, `Read`, `Edit`, …). |
| `args_digest`  | string | yes      | `sha256:` prefix + 64 hex; used by `kata skill suggest` for shape clustering. |
| `bash_argv0`   | string | no       | First token of the argv when `tool` is `Bash`; `null` otherwise. |
| `tokens_in`    | int    | no       | Tokens consumed by the call, if the adapter can provide. |
| `tokens_out`   | int    | no       | Tokens emitted by the call, if the adapter can provide. |
| `duration_ms`  | int    | no       | Wall-clock duration, if the adapter can provide. |

## Args sidecar row (JSONL)

One JSON object per row, schema-free — raw args as the adapter saw
them. Row index implicitly aligns with the shape row's order in the
shape file for the same session.

## Privacy & retention

- Both tiers are gitignored by default (`.gitignore` excludes
  everything under `.antoine/` except `katas.toml`).
- `kata log gc` (default TTL 7 days) deletes args files past TTL
  *first*, then shape files. If any unlink fails, gc exits non-zero
  and antoine refuses to silently retain expired data.

## Who writes this?

antoine itself does NOT write to the log during normal operation. The
agent's backend writes (via project hooks, transcript ingest, or
self-emit — see `kata learn`). antoine only reads, prunes, and reports.
