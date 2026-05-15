# Judge rubric (v1)

You are scoring one of two answers (`answer_X`, `answer_Y`) to the
same question. Both answers came from the same model under the same
prompt; one was equipped with a `repo-map` skill, the other was not.

Score on these dimensions, in priority order:

1. **Factual correctness.** Are the claims about the repo true?
   Penalise unsupported assertions, invented file paths, and wrong
   dependency names.
2. **Completeness vs. the question scope.** A "what is this repo"
   question should cover purpose, build/test, and top-level
   structure. A "what does this connect to" question should name the
   actual connections.
3. **Actionability.** If the asker is going to do something with the
   answer (port a CI pipeline, build a similar CLI), can they?
4. **Restraint.** Penalise irrelevant detail, repetition, and padding.

Pick a winner: `X`, `Y`, or `tie`. Pick a margin: `tie`, `slight`,
`clear`, `decisive`. Justify in **one short sentence** of reasoning —
the reasoning is for spot-check, not for the asker.

Output a single-line JSON object:

    {"winner": "X" | "Y" | "tie", "margin": "tie" | "slight" | "clear" | "decisive", "reasoning": "..."}

No prose outside the JSON.
