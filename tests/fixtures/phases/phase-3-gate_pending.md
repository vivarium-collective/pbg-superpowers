---
phase: 3
name: Replication forks
status: gate_pending
prereq_phases: [2]
gate_passed: false
opened_pr: 11
acceptance_tests:
  - id: phase-3.t1
    desc: Bidirectional fork progression
    status: failing
parameters_added:
  - { name: fork_speed, value: 1000.0, unit: bp_per_s }
deliverables:
  code_diff: deliverables/phase-3-diff.md
  plots: [deliverables/phase-3-traces.png]
  test_report: deliverables/phase-3-tests.md
open_questions: [phase-3.q1, phase-3.q2]
---

## Phase 3: Replication forks
### Objective
Bidirectional fork progression.
### Phase Gate
All forks reach ter sites within expected time.
