---
phase: 2
name: Initiation trigger
status: in_progress
prereq_phases: [1]
gate_passed: false
opened_pr: 9
acceptance_tests:
  - id: phase-2.t1
    desc: DnaA threshold fires oriC
    status: pending
---

## Phase 2: Initiation trigger
### Objective
Threshold-fire of oriC.
### Required Biological Knowledge
### Implementation Tasks
- Add oriC_state store
- Wire DnaA threshold check
### Readouts / Visualizations
### Expected Behavior
### Acceptance Tests
### Failure Modes
### Phase Gate
### Deliverables
