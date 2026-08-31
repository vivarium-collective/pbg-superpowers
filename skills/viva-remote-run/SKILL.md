---
name: viva-remote-run
description: Use when running a workspace composite remotely on viva-api (the GovCloud simulation backend) — via the vivarium-workbench remote-run flow or the API directly, instead of locally. Covers connecting, choosing the run path (generic compose/run_pbg vs the legacy comparison view), submit params, the emit/store model, how a data-prep pipeline that is itself a composite dissolves cache-provisioning, and the API gotchas that each cost real debugging time.
user-invocable: true
allowed-tools: Bash(*) Read
argument-hint: connect | submit | status | fetch  (or just read it as a runbook)
---

# /viva-remote-run

Run a workspace composite on **viva-api** (the GovCloud simulation backend) and
get its results back. This is the *remote* sibling of [`/viva-run`](../viva-run/SKILL.md)
(local composite smoke-test) — same idea, but the sim executes on GovCloud Ray and
emits to S3. The interactive [`/viva-workbench`](../viva-workbench/SKILL.md) server
is what a human drives; this skill is the run-path + params + gotchas the agent
needs to actually land a remote run.

This skill is **framework-generic** — it describes how *any* workspace composite
runs on viva-api. Domain specifics (which composite, which config, which KPI leaf)
belong in that domain's own repo docs, never here.

> **Provenance / freshness.** The endpoint/param specifics were verified against a
> deployed viva-api release and its `origin/main` `viva_api/` code during a live
> session. viva-api ships fast (several patch versions in a day). **Treat
> version-dependent specifics as "verify, don't trust"** — the architecture and the
> gotcha *classes* are stable; exact endpoint behavior may have moved. See the
> house rule at the end.

## Names & repos

- **viva-api** = repo `vivarium-collective/sms-api` (the `sms-api` name redirects
  to `viva-api`; on `main` the package was renamed `sms_api/` → `viva_api/`).
  Owners: **Jim Schaff** (`jcschaff`), **Alex Patrie** (`AlexPatrie`).
- **workbench** = `vivarium-workbench`, drives viva-api via `lib/sms_api_client.py`.
- GovCloud stack prefix is **`smsvpctest`** (`sms-cdk` is *not* renamed).
- The dashboard API reads the **local** workspace; **viva-api** is the **backend**
  that launches runs and stores results on S3. The dashboard *consumes* viva-api.

## 1. Connect (laptop → GovCloud)

1. `aws sso login --profile stanford-sso` (region `us-gov-west-1`; token expires —
   re-run per session). This is an **interactive** login — have the user run it
   (`! aws sso login --profile stanford-sso`).
2. SSM tunnel to the internal ALB:
   `AWS_PROFILE=stanford-sso AWS_DEFAULT_REGION=us-gov-west-1 bash ~/code/sms-cdk/scripts/ptools-proxy.sh -s smsvpctest`
   → forwards `localhost:8080`. **The tunnel drops constantly** (`http_code=000` /
   "Exiting session"); restart before every burst: `pkill -f session-manager-plugin`
   then re-run. Verify with `curl localhost:8080/version`.
3. S3 is independent of the tunnel (`stanford-sso` profile):
   `s3://smsvpctest-shared-sharedbucket…/` under viva-api's fixed output layout —
   `vecoli-output/<experiment_id>/`, `ray-parca-cache/<commit>/`, `ray-logs/`.
   (Those prefix names, and the `run_parca` submit param below, are viva-api's own
   historical interface names — backend facts, not something this skill models.)

## 2. Choose the run path — this is the crux

Pick by *what you need emitted*, because **what gets emitted is a property of the
composite's own declared emitter, not viva-api** (§4).

| Path | Endpoint | Emits | Use when |
|---|---|---|---|
| **Generic compose** | `POST /compose/v1/simulation/run` | whatever the composite's own emitter declares | the target direction (viva-api #343). Requires the composite to be **provisioned** into the compose image — see §5 |
| **Legacy `/api/v1`** | `POST /api/v1/simulations` | a **fixed curated comparison view** (a small set of scalars) when a domain `composite` is named; a fuller path when it routes to the generic runner | quick comparison scalars; **being retired** (#343) |

The single biggest trap: naming a **domain `composite`** on `/api/v1` can route
you to a **curated, fixed emit-view** that excludes most observables *by
construction*. If a KPI is "missing" from the store, you're almost certainly on a
curated view — use the generic compose path (or the generic branch of `/api/v1`)
so the composite's own emitter runs. **Verify which branch you hit** against the
current deploy — the routing is version-dependent.

## 3. Submit — prefer workbench-driven over raw curl

Raw curls silently drop params (see §6). The workbench assembles the **full**
param set from the workspace/study spec, so prefer it:

- `vivarium_workbench/lib/sms_api_client.py`:
  - `run_simulation(*, simulator_id, num_generations, num_seeds, run_parca, observables, …)`
    → `POST /api/v1/simulations` (legacy). `run_parca` is a **required** kwarg;
    `observables` becomes repeated query keys.
  - `compose_submit(pbg_bytes, extra_pip_deps, interval_time, filename)`
    → `POST /compose/v1/simulation/run` (multipart process-bigraph `.pbg` document).
- `lib/remote_run.run_remote(ws_root, composite_id, n_steps, overrides, …)` — the
  deployment-target flow: `export_composite_pbg` → `compose_submit` → poll →
  download `results.zip`. Sends `extra_pip_deps=[git+<workspace repo>@<sha>, pins]`.
- `lib/remote_run_jobs.run_remote_pipeline` — legacy: push → build image
  (`/core/v1/simulator/upload` from a git ref) → `run_simulation` → poll → land.

**Both are live** (the workbench is mid-migration off legacy); the migration is to
move `run_simulation` callers onto `run_remote`.

## 4. Emit / observables — why a KPI can be "missing"

A composite declares its own emitter, e.g.:
```python
emitters=[{"address": "local:ParquetEmitter", "config": {}, "paths": ["global_time", "bulk", "listeners"]}]
```
On any **full-emit** path viva-api writes exactly those declared paths — nothing is
added or removed by viva-api; `_redirect_emitters` only changes the output
*location* (→ S3), never *what* is emitted. So:

- If your composite's emitter declares the subtree your KPI lives in, it's in the
  store on a full-emit path — **no extra "observable" flags needed**.
- A **curated comparison view** emits only its fixed path set → anything outside it
  is excluded *by construction*. The right fix is to run a full-emit path, **not**
  to add domain-specific observable flags into viva-api (that would push domain
  knowledge into the generic backend).

Store shape: partitioned `…/variant=/lineage_seed=/generation=/agent_id=/`.
**Confirm the actual columns/partitioning against a real store before writing a
reader** — how the emitter flattens node/dict leaves into columns is a "the store
will tell you, don't assert it" detail. And **check the timepoint density**: a
remote run has been seen emit far fewer timepoints/generation than a local run, and
a coarse trace makes a remote-vs-local statistic not like-for-like.

## 5. Provisioning & caches — a data-prep pipeline that is itself a composite

Two provisioning realities:

- **Compose image.** The `/compose/v1` Ray backend runs a *prebuilt workspace
  image* (`COMPOSE_RAY_IMAGE_TAG`) and can be **generic-only** on a given deploy
  (base Python + framework, no workspace composites baked in). Running *your*
  workspace composite through `/compose/v1` needs a workspace image built from
  **your repo @ commit** (git-deps + framework) pushed to the ray ECR repo + the
  tag set. That's deploy/infra work (Jim & Alex or deploy access) — there may be no
  existing pipeline that bakes a specific workspace into the compose image.

- **Input-data caches (the key move).** If your simulator needs a prepared input
  (a fitted parameter set, a compiled knowledge base, etc.) and **that preparation
  is itself a composite**, you do **not** need viva-api to select or stage a cache
  per run — you *build the cache by running that prep composite through the same
  compose path*:
  - **Option A** — one document: prep-composite → sim-composite (self-contained).
  - **Option B** — a prep-composite run emits the cached input → a second
    sim-composite run consumes it (build once, fan out).
  This dissolves "per-run cache selection" entirely and keeps **viva-api generic**
  — the capability lives in your composites, not the backend.

Cache cautions (when a cache *is* pre-staged rather than composite-built):
- A config path that **404s can silently fall back to a default/basal template**
  → a run that looks successful but ran the wrong inputs. Pass a config path that
  exists in the sim's image repo, and prefer failing loud on not-found.
- **Pre-staged caches are version-tied** — a cache-version check hashes source
  files, so a pre-built cache must match the code pin inside the sim image or it
  errors. Composite-built caches sidestep this (they build against the running
  code). Stage to **labeled** paths (`…/<commit>/<variant>/`), never a bare commit
  key (that clobbers a shared baseline every concurrent run relies on).

## 6. Gotchas — each one cost real time

- **`run_parca=true` (or the equivalent "run the prep step") is required** for a
  config-driven input build; omit it and you get a phantom run (`job_id=null`,
  empty output).
- **A "generations" submit param may not be the one the driver reads.** One field
  sets the config; the *driver* may read a different field (e.g. a
  `max_*generations` that **defaults to 1**) — so a multi-gen config with the wrong
  field set runs ONE generation. Verify which field the driver consumes.
- **Output prefix = the config's internal `experiment_id`**, not the submit's
  `experiment_id` param — watch the right S3 prefix.
- **A results endpoint can return HTTP 200 `[]` while the files exist** in S3 — a
  false "produced nothing." Pull `result_uri` from the run record and `aws s3 cp`.
- **The submit `{id}` may be the *simulation* id, not the analysis id** —
  `/analyses/<sim-id>/status` can 404; resolve via
  `/api/v1/simulations/{id}/analyses → database_id`.
- **The tunnel drops constantly** — restart before every viva-api burst.
- **Local API checkouts go stale fast** — read `origin/main` (mind the package
  rename), not a local branch, when reasoning about server behavior.
- **`s3fs` + `zarr3` async loop** breaks on repeated reads — `aws s3 cp` the store
  local and open from disk.
- **Multi-seed remote is unproven** until acceptance-tested against a known local
  number — don't trust an N-seed ensemble without that anchor.

## 7. Direction (viva-api #343)

Retire the `/api/v1/simulations` comparison driver; standardize on the generic
`/compose/v1` `run_pbg`. **Emit-selection stays a composite property; input
preparation runs as a composite; viva-api stays completely generic** (no domain
knowledge). The workbench migrates `run_simulation` callers onto `run_remote`;
deploy provisions the workspace compose image.

## House rule: verify against the current deploy, don't guess

This integration moved several versions *within a single session*, and every wrong
turn came from trusting a stale assumption (a local checkout, an inferred endpoint
behavior, a guessed param). So:

- **Read `origin/main` server code**, not a local API checkout, when you need to
  know what the server does.
- **Probe-and-cancel** to learn endpoint behavior empirically (submit, read the
  echoed built config, cancel before compute) rather than asserting from
  deploy-branch source you can't confirm is deployed.
- **Confirm the store's actual columns/partitioning** before writing a reader.

## See also

- [`/viva-run`](../viva-run/SKILL.md) — local composite smoke-test (the fast, offline sibling).
- [`/viva-workbench`](../viva-workbench/SKILL.md) — the interactive dashboard server a human drives.
- `vivarium-workbench` `docs/dashboard-api-vs-sms-api.md` — the local-API ↔ viva-api boundary.
