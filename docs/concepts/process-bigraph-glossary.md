# Process-Bigraph Glossary

Canonical terminology for the Process-Bigraph framework. Bigger-picture framing is anchored on the main paper ([Agmon & Spangler, 2026 main](../references/papers/agmon-spangler-2026-process-bigraphs-main.pdf)); formal semantics on the supplement ([Agmon & Spangler, 2026 supplement 1](../references/papers/agmon-spangler-2026-process-bigraphs-supplement1.pdf)). Use these names exactly when authoring skill docs, plans, specs, or code comments.

## Bigger picture

### Compositional systems biology — what the framework is for

Process Bigraph is a *composition protocol* for systems biology — analogous to how internet protocols let heterogeneous computers interoperate. It operates one level above individual model descriptions (SBML, CellML, etc.), specifying how multiple models, datasets, and simulators are connected, how data is exchanged, and how execution is coordinated. The shift from "publish a single model" to "compose models into a multiscale simulation" is what *compositional systems biology* names.

### Three fundamental criteria for compositional modeling

| Criterion | What it specifies |
|---|---|
| **Process interfaces** | The precise points of interaction between mechanisms and system state — which variables a process reads, writes, or transforms. |
| **Composition patterns** | How independently developed processes are coupled through shared state. Includes the place graph (hierarchical containment) + the process graph (wiring of processes to stores). |
| **Orchestration patterns** | How processes are invoked over time, with consistent access to shared state. Determines temporal coordination across heterogeneous timescales. |

### Three orchestration patterns

| Pattern | When to use | Mechanism |
|---|---|---|
| **Multi-timestepping** | Continuous + discrete processes on different timescales. | DEVS-style scheduling; each process declares an `interval`; the composite invokes the next-due event. |
| **Workflows** | Initialization, analysis pipelines, computation with natural ordering. | DAG of `Step` nodes (interval = 0); each step runs after its input dependencies are satisfied. |
| **Event-driven structural updates** | Composite must change its own structure (division, engulfment, bursting). | Graph-rewrite processes apply structural deltas in response to state-dependent conditions. |

All three patterns are interoperable; entire composites can themselves act as processes within larger composites, so multi-scale orchestration is recursive.

### Place graph and process graph

The framework builds on Milner's bigraphs, which combine a **place graph** (hierarchical containment — e.g. molecules in compartments, cells in tissues) and a **link graph** (connectivity via hyperedges). Process Bigraph keeps the place graph and replaces the link graph with a **process graph** in which processes are first-class nodes connecting to stores via typed ports. This shift emphasizes dynamics and causation: rather than encoding interactions implicitly as links, processes are entities that condition on, and act upon, the evolving system.

## Software stack

- **bigraph-schema** — foundational library; defines the type system and hierarchical data structures using JSON-based schemas. Provides the **type engine** (`Core` class) and the global `type_registry`.
- **process-bigraph** — dynamic core; defines `Process`, `Step`, `Composite`, and event-scheduling/orchestration logic.
- **bigraph-viz** — visualization library; parses JSON representations and renders graphs.
- **spatio-flux** — domain example: metabolic processes, field dynamics, particle dynamics, coupled particle–field interactions.
- **pbg-superpowers** — repository of reusable AI agent skills for scaffolding process wrappers, adapters, and composite connection patterns. (THIS REPO.)

## Mathematical preliminaries

| Symbol | Name | Definition |
|---|---|---|
| 𝓜 | Marks | Set of atomic path components. |
| 𝒫 = 𝓜* | Paths | Finite paths, implemented as lists of marks (e.g. `["organism", "cell", "mass"]`). |
| 𝒯 | Types | Set of types. |
| 𝒱 | Values | Set of values. |
| StorePath ⊆ 𝒫 | Store paths | Paths designating locations where concrete values may be stored. |
| Σ : 𝒫 ⇀ 𝒯 | **Schema tree** | Partial map assigning a type to each path in a JSON-like hierarchy. |
| x : 𝒫 ⇀ 𝒱 | **State tree** | Partial map assigning concrete values to paths. |
| Σ ⊢ x : State | **Typing judgment** | "Under schema Σ, the state tree x is a well-formed state." |
| R_T | **type_registry** | Global registry mapping types to their validation + update semantics. |
| R_L : Address → HandlerClass | **link_registry** | Global registry mapping process addresses to handler classes. |
| W : (LinkPath × PortName) → 𝒫 | **Wiring map** | Derived (not stored separately) from the `inputs`/`outputs` fields stored in the state tree. |

## Links, ports, and wiring

- **Link** — a node whose schema specifies a typed interface.
- **Port** — a named, typed input or output on a link. Each port has a declared type `τ_ℓ = Σ(p.ℓ)`.
- **Process node** — a specialized link with `address`, `config`, `interval`, and typed input/output ports.
- **inputs / outputs** — fields on a link node in the state tree, mapping port names to **state-tree paths**.
- **Wiring is well-typed** when each port is connected to a state path whose schema type matches the port's declared type.

## Processes and delta semantics

- **Process** — a specialized link with runtime fields:
  - `address` — identifies the concrete handler class (resolved via `link_registry`).
  - `config` — process-specific parameters subtree.
  - `interval` — nominal time advance.
  - typed input/output ports.
- **Step** — a process with `interval = 0`. Steps participate in DAG-style topological execution within a single tick.
- **update method** — the contract: `update : (config^τ_c, in_1^τ, ...) ⟶ Δ`. The handler reads projected inputs and returns a **delta**.
- **Delta (Δ)** — a description of how the state should change. Three categories:
  - **Primitive deltas** — leaf-level updates applied to non-structured values (e.g. scalar increment `x' = apply_τ(x, δ)`).
  - **Composite deltas** — tree-structured updates, one branch per output port.
  - **Structural deltas** — modify the shape of the state tree or schema tree: `insert`, `delete`, `move`, `rewrite`, `rewire`. Represent graph-level changes (division, merging, engulfment, spawning) as ordinary typed deltas.
- **apply_τ : V_τ × Δ_τ → V_τ** — the type-specific update operator. Examples in Table S1 of the supplement: `apply_float`, `apply_array`, `apply_conc_counts`, `apply_map`.

## Single-process update protocol (3 stages)

For a process at path p_proc:

1. **Input projection** — `x_in(ℓ) = x(W(p_proc, ℓ))` for each input port ℓ.
2. **Evaluation** — `δ = update_{p_proc}(x_in, Δt)`. Result is a delta structured by the process's output ports.
3. **Application** — for each output port ℓ, let `q = W(p_proc, ℓ)`, `τ = Σ(q)`; apply `x'(q) = apply_τ(x(q), δ(ℓ))`.

## Process-Bigraph (the data structure)

A **Process-Bigraph** is the tuple `B = (Σ, x, R_T, R_L)` with three consistency conditions:

1. **Type correctness** — the typing judgment `Σ ⊢ x : State` holds.
2. **Well-typed wiring** — every port's schema type matches the schema type at its wired destination path.
3. **Well-formed processes** — every process node in `LinkPath` has a valid `address` in `R_L` and a configured handler instance stored at the same path.

The global wiring map `W` is derived from the `inputs`/`outputs` fields stored in `x`.

## Composite

A **Composite** is a specialized `process` whose configuration encodes an entire process-bigraph (schema tree, state tree, type_registry, link_registry). It additionally declares:

- an **interface** — typed input/output ports forming the external API;
- a **bridge** — mapping interface ports to internal state-tree paths.

Operationally `C = (Σ_state, x_state, R_T, R_L, bridge, interface)`. Composites provide hierarchical modularity: externally a single process, internally a complete process-bigraph.

## Orchestration

Inspired by DEVS (Discrete Event System Specification). The composite maintains:

- a global time `t ∈ ℝ_{≥0}`,
- a schedule `t_next : LinkPath → ℝ_{≥0}` mapping each process to its next event time.

**Small-step semantics**: configuration `⟨B, t, t_next⟩` transitions to `⟨B', t', t'_next⟩` via:

- **(Select)** — pick `t* = min_p t_next(p)` and the set `S = {p | t_next(p) = t*}`. Advance global time to `t' = t*`.
- **(Process Update)** — for each `p ∈ S`: input projection + invoke handler + apply output deltas.
- **(Reschedule)** — `t'_next(p) = t' + interval(p)` for persisting processes.

### Update reconciliation

When multiple processes update the same store in one tick, deltas are reconciled before application. A **reconciler** (attached to a type via `R_T`) maps `(δ_1, ..., δ_n) ↦ δ*`. Used for non-commutative updates (e.g. structural deltas where insertion vs. deletion order matters).

### DAG-structured discrete workflows

When all processes in a subsystem have `interval = 0`, scheduling reduces to a DAG over `Step` nodes:

- A step is **eligible** when all input ports updated this tick have received new values.
- Inputs unchanged in this tick do not block execution.
- Topological order is enforced; cycles disallowed.

A Composite can appear as a `step` in a larger DAG → end-to-end workflows.

### Large-scale orchestration pipeline

`run(Δt)` advances simulation by repeatedly invoking:

1. **Partition** — separate scheduled processes by execution protocol.
2. **Invoke** — four substeps per process: *Slice* (project state), *Interval* (compute Δt via `calculate_timestep`), *Invoke* (call handler), *Stash* (record delta + reached time).
3. **Flush** — collate returned deltas.
4. **Apply** — three substeps: *Combine* (gather by store path), *Reconcile* (resolve via type's reconciler), *Apply* (use `apply_τ`).

## Emitters

An **Emitter** is a specialized `Step` whose role is **observational**: declares typed input ports, no semantic outputs into the simulation state. At execution time, reads values from its inputs and writes to an external or side-channel store (in-memory, disk, streaming log) for later retrieval. Emitters do not introduce data dependencies and cannot affect subsequent process execution.

## Protocols

Process execution protocols define how addresses resolve to running handlers:

| Protocol | Module | Behavior |
|---|---|---|
| `local_lookup_module` | `bigraph_schema.protocols.local_lookup_module` | Processes instantiated as Python objects in-runtime; in-memory function calls. |
| `parallel` | `multiprocessing.Pipe` | Each process in a separate OS process; state serialized across the boundary. |
| `rest` | HTTP | Process address → (process_class, host, port); state serialized into request payloads. |
| `ray` | Ray actors | Each unique (process_class, config) tied to a persistent actor pool (default size `os.cpu_count()`); round-robin dispatch. |
| (variants) | `docker`, `socket` | Explored historically; not in the current active registry. |

## Concrete reference: Spatio-Flux process families

From the main paper's Table 2. Useful as a categorization when scaffolding a new process: "is this a metabolic process? a field transport process? ..." helps pick the right wrapper pattern.

| Family | Example processes | Role |
|---|---|---|
| Metabolic | `DynamicFBA`, `MonodKinetics`, `SpatialDFBA` | Compute metabolic uptake, secretion, biomass production. |
| Field transport | `DiffusionAdvection` | Update dissolved-species fields through diffusion and advection. |
| Particle movement | `BrownianMovement`, `PymunkParticleMovement` | Update particle positions in continuous space (stochastic / Newtonian). |
| Particle–field coupling | `ParticleExchange` | Bidirectional exchange between particle-local state and spatial fields. |
| Structural / boundary | `ParticleDivision`, `ManageBoundaries` | Rewrite the particle store (creation, removal, boundary handling). |

## See also

- `docs/concepts/vivarium-workbench-model.md` — the dashboard's view of workspaces, studies, runs.
- `docs/concepts/expected-behavior-grammar.md` — DSL for encoding scientific predictions as testable (given, measure, expect) triples in study.yaml.
- `docs/conventions/composites.md`, `docs/conventions/composite_generators.md` — implementation conventions.
- `docs/conventions/visualizations.md`, `docs/conventions/discovery.md`, `docs/conventions/distribution.md` — implementation conventions.
- The supplement PDF for the full mathematical treatment, the Michaelis–Menten worked example (Figs. S1, S2), and Table S1 of update operators.
