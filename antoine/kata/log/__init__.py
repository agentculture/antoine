"""Log subsystem: JSONL schema, on-disk store, TTL gc.

Layout (under the current working directory):

  .antoine/log/<YYYY-MM-DD>.jsonl    shape index, one line per tool call
  .antoine/log/args/<session>.jsonl  raw args sidecar, keyed by row index

The shape index is what `suggest`/`assess` read. The args sidecar holds
raw, privacy-sensitive data and is the first thing the 7-day TTL pass
deletes.
"""
