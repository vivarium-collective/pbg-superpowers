# suite-v1 — study-automation benchmark starter suite

Items the `/viva-benchmark` skill runs through the autonomous model-building loop.
Each is a `{id, question, domain, difficulty, expected_mechanisms, solvable, notes}`
YAML. `solvable: false` items are integrity controls — the loop MUST give up
honestly; a "pass" there is a gamed pass the rubric scores `mismatch`.
