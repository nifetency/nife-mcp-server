# Spec: static-site release-strategy tools

Status: draft, not implemented.
Scope: blue-green deployments, canary releases and A/B tests for **static sites** (S3 deployments).
Sources: `nife.io/api/s3_advanced.graphqls` and `s3_advanced.resolvers.go`. Everything below that
says "the backend does X" was read from those resolvers. Anything not visible there (the `service`
package) is listed under "Open questions" and must be checked before implementation.

Today the connector can only read this area: `list_site_releases` and `get_release_details`.
This spec adds the write side as 10 tools in `site_tools.py` (or a new `release_tools.py`).

---

## 1. What the backend does (and what that means for the tools)

| Finding | Consequence for the tools |
|---|---|
| Creating a blue-green deployment, canary or A/B test checks the plan quota (`BlueGreen`, `Canary`, `ABTesting`), the credit balance and the spending limit. Failures come back as plan-limit errors. | Creation is billable. Instructions tell the model to confirm with the user first, and plan-limit errors are passed through with a pointer to `get_plan_limits` and `get_credits`. |
| Cost assumptions in the resolvers: blue-green doubles resources for a 2-hour window, a canary runs about 24 h scaled by its traffic percent, an experiment about 72 h, an A/B test about 7 days. | Quote these in the tool descriptions as estimates, never as exact prices. |
| `autoPromote` is forced to `false` ("automatic promotion isn't implemented; promote by hand"), although the schema defaults it to `true` for canaries. | Do **not** expose `auto_promote` or `promote_threshold`. Promotion is always an explicit `promote_site_experiment` call. |
| `stopS3Experiment(reason)` and `abortS3Experiment(reason)` ignore `reason`. | `abort` still requires a reason (it is echoed back for the user's record), but the tool must say the backend does not store it. |
| Mutations (`switch`, `rollback`, `complete`, `start`, `stop`, `promote`, `abort`, `scale`) only pass `user.ID` into `service.*`. The access check that the queries do (`CheckS3DeploymentUser`) is not visible in the resolvers. | **Every tool reads the object through the access-checked query first** (`getS3BlueGreenDeployment`, `getS3Experiment`) and only then mutates, the same ownership pattern as `_require_app`. Never accept an id the caller was not shown. Also see Open questions. |
| `getS3ExperimentMetrics` builds `controlMetrics` and `treatmentMetrics` from the same call (`GetMetricsForApp(app, "performance")` twice), so both lists are identical and not split by version. | The tools must not present them as a control-vs-treatment comparison. `get_release_details` should split rows by `deploymentVersion` itself (section 5). |
| `checkS3BlueGreenHealth` returns per-slot health (`healthy`, `status_code`, `response_time_ms`, `error`) and `overallHealthy` = both slots healthy. | `switch_site_blue_green` uses it as a pre-flight check. |
| The first switch goes to green; blue is the version serving today (schema comment). | `blue_version` defaults to the site's live version. |
| Status strings in the schema comments: blue-green `preparing`, `ready`, `switching`, `active`, `rolling_back`; experiments `draft`, `active`, `completed`, `aborted` (plus a "stopped" status in the service layer). | Treat statuses as case-insensitive strings and check them with allow-lists in one helper, so a wrong guess fails with a clear message instead of a backend error. |

## 2. Common rules

1. **Ownership first.** Load the site with `require_site`, then the deployment or experiment with the
   access-checked query, and confirm `appName` equals the site named by the caller.
2. **Direction of travel decides confirmation.**
   - Moves visitors onto a new version, or makes a change permanent: needs `confirm=true`, and previews
     without it (like `vm_power_action` and `trigger_cron_job_run`). That covers `switch`, `complete`,
     `start`, `promote`, and `scale` when the percentage goes up.
   - Returns visitors to the normal release (`rollback`, `stop`, `abort`, scaling down): no `confirm`.
     Speed matters in an incident.
3. **No concurrent strategies.** Before creating anything, read `getS3DeploymentStrategySummary` and
   refuse if a blue-green deployment or experiment is already active for the site (the backend rule is
   unverified, so the safe choice is to refuse and name the blocker).
4. **Versions come from history.** Validate every version against `deployments_list(site)`; reject
   unknown versions, identical control and treatment versions, and versions whose status is a failure.
5. **No secrets in or out.** No tool takes or returns credentials. Health-check URLs must be `https`
   and pass `h.validate_archive_url`-style checks (no private or loopback IP literals).
6. **Annotations** from `tool_utils`: `DESTRUCTIVE` for tools that change live traffic or permanence,
   `WRITE` for creation and for returning to the normal release.
7. **Return shape.** `{ "<verb>": true, "site_name", "<id>", ..., "next_step": "..." }`, like the app
   tools. Backend text is passed through after the same truncation as other tools.

## 3. Tools

### Blue-green

| Tool | Annotation | GraphQL | Confirm |
|---|---|---|---|
| `create_site_blue_green` | WRITE | `createS3BlueGreenDeployment` | no (instructions require user approval, billable) |
| `switch_site_blue_green` | DESTRUCTIVE | `switchS3BlueGreenSlot` | yes |
| `rollback_site_blue_green` | WRITE | `rollbackS3BlueGreen` | no |
| `complete_site_blue_green` | DESTRUCTIVE | `completeS3BlueGreen` | yes |

**`create_site_blue_green`**
- Params: `site_name`; `green_version` (the new version to test); `blue_version` (default: the live
  version); `switch_strategy` `instant|gradual` (default `instant`); `health_check_url` (optional,
  https); `health_check_interval_seconds` 10 to 3600 (default 30); `rollback_threshold_error_rate`
  0.1 to 50 (default 5.0).
- Flow: `require_site`, not suspended, no active strategy (rule 3), versions valid (rule 4), mutation.
- Returns: deployment id, both slot URLs, status, `next_step`: "Call get_release_details to check slot
  health, then switch_site_blue_green."
- Description must say: billable, doubles hosting resources for the switch window, needs a plan that
  includes blue-green.

**`switch_site_blue_green`**
- Params: `deployment_id`, `confirm=false`, `allow_unhealthy=false`.
- Flow: load deployment, status must be one that can switch (`ready` or `active`), run
  `checkS3BlueGreenHealth`. Without `confirm`: return a preview (current slot, target slot, versions,
  per-slot health). Refuse if the target slot is unhealthy unless `allow_unhealthy=true`. With `confirm`:
  mutate, then re-read and report the new active slot.
- Description must say: ALL traffic moves to the other slot at once, and the first switch goes to green.

**`rollback_site_blue_green`**
- Params: `deployment_id`. Stops blue-green routing; the site serves its normal release again.
  Allowed from any non-terminal status.

**`complete_site_blue_green`**
- Params: `deployment_id`, `confirm=false`.
- Precondition: the deployment has been switched (`switchedAt` set). The serving slot's version becomes
  the site's release and blue-green routing ends. Preview shows which version becomes permanent.

### Canary and A/B

| Tool | Annotation | GraphQL | Confirm |
|---|---|---|---|
| `create_site_canary` | WRITE | `createS3CanaryDeployment` | no (billable; instructions) |
| `create_site_ab_test` | WRITE | `createS3ABTest` | no (billable; instructions) |
| `start_site_experiment` | DESTRUCTIVE | `startS3Experiment` | yes |
| `scale_site_canary_traffic` | DESTRUCTIVE | `scaleS3CanaryTraffic` | yes when increasing |
| `promote_site_experiment` | DESTRUCTIVE | `promoteS3Experiment` | yes |
| `stop_site_experiment` | WRITE | `stopS3Experiment` / `abortS3Experiment` | no |

**`create_site_canary`**
- Params: `site_name`, `canary_version`, `control_version` (default: live version),
  `initial_traffic_percent` 1 to 50 (default 10).
- The experiment is created in `draft`; nothing reaches visitors until `start_site_experiment`.
  Say so in the description and in `next_step`.

**`create_site_ab_test`**
- Params: `site_name`, `experiment_name` (1 to 80 chars, no control characters), `treatment_version`,
  `control_version` (default: live version), `treatment_percent` 1 to 99 (default 50). The tool sends
  `trafficSplit = {"control": 100 - p, "treatment": p}`.
- Success metrics and promote thresholds use the backend defaults; they are not exposed (see section 1).
- Created in `draft`, like the canary.

**`start_site_experiment`**
- Params: `experiment_id`, `confirm=false`. Status must be `draft`. Preview states the percentage of
  visitors who will get the treatment version.

**`scale_site_canary_traffic`**
- Params: `experiment_id`, `traffic_percent` 0 to 100, `confirm=false`.
- Only for experiments of type `canary`. Read the current percentage first. Increasing needs `confirm`;
  decreasing does not. If the jump is larger than 25 points, the preview adds a warning to go in steps
  while watching `get_site_analytics`.

**`promote_site_experiment`**
- Params: `experiment_id`, `confirm=false`. Status must be `active`. Preview shows control and
  treatment versions and the per-version metrics (section 5). After confirmation the treatment version
  becomes the site's release permanently. Description states that automatic promotion does not exist.

**`stop_site_experiment`**
- Params: `experiment_id`, `outcome` `stop|abort` (default `stop`), `reason` (required for `abort`,
  1 to 300 chars).
- Maps to `stopS3Experiment` or `abortS3Experiment`. Visitors go back to the normal release. Say that
  the backend does not store `reason`.

### Deliberately not exposed

| Operation | Why |
|---|---|
| `createS3Experiment` | `createS3ABTest` and `createS3CanaryDeployment` cover its real uses; its free-form `experimentType` invites invalid combinations |
| `recordS3Metric`, `collectS3Metrics` | Metrics ingestion, not something an assistant should write; `recordS3Metric` shows no ownership check in the resolver |
| `migrateS3Organization` | Bulk cross-organization move; admin-level and out of scope |

## 4. Client methods to add to `NifeAPI`

One method per mutation, each with the exact GraphQL operation and a long timeout where the backend
touches the CDN (120 s):

```python
async def create_blue_green(self, input_): ...   # createS3BlueGreenDeployment(input: S3BlueGreenDeploymentInput!)
async def switch_blue_green(self, deployment_id): ...    # switchS3BlueGreenSlot(deploymentId: String!)
async def rollback_blue_green(self, deployment_id): ...  # rollbackS3BlueGreen(deploymentId: String!)
async def complete_blue_green(self, deployment_id): ...  # completeS3BlueGreen(deploymentId: String!)
async def create_canary(self, input_): ...       # createS3CanaryDeployment(input: S3CanaryDeploymentInput!)
async def create_ab_test(self, input_): ...      # createS3ABTest(input: S3ExperimentInput!)
async def start_experiment(self, experiment_id): ...     # startS3Experiment(experimentId: String!)
async def scale_canary(self, experiment_id, percent): ...# scaleS3CanaryTraffic(input: S3TrafficScaleInput!)
async def promote_experiment(self, experiment_id): ...   # promoteS3Experiment(experimentId: String!)
async def stop_experiment(self, experiment_id, reason): ...  # stopS3Experiment(experimentId, reason)
async def abort_experiment(self, experiment_id, reason): ... # abortS3Experiment(experimentId, reason: String!)
```

`blue_green`, `blue_green_health`, `experiment`, `experiment_metrics`, `strategy_summary` and
`deployments_list` already exist.

## 5. Change to an existing tool: `get_release_details`

Because the backend returns identical control and treatment metric lists, group the returned rows by
`deploymentVersion` and report, per version: sample count, mean of each `metricName`, and the latest
timestamp. If a version has no rows, say "no metrics recorded for this version yet" instead of showing
the other version's numbers. Add a `note` explaining the backend limitation. This protects users from
promoting on a comparison that is not real.

## 6. Text to add to `SERVER_INSTRUCTIONS`

```
SITE RELEASES (blue-green, canary, A/B)
- Start with list_site_releases. Only one strategy can run on a site at a time.
- Creating a blue-green deployment, canary or A/B test is billable and needs a plan that includes it:
  confirm version(s) and, for A/B, the traffic percentage with the user first.
- Blue-green: create_site_blue_green, check slot health with get_release_details, then
  switch_site_blue_green (moves ALL traffic), then complete_site_blue_green to make it permanent, or
  rollback_site_blue_green to undo.
- Canary / A/B: create_*, start_site_experiment, watch get_release_details and get_site_analytics,
  raise a canary with scale_site_canary_traffic in small steps, then promote_site_experiment or
  stop_site_experiment. Promotion is never automatic.
- Tools that move visitors onto a new version or make a change permanent need confirm=true after the
  user agrees. Rolling back, stopping and aborting return visitors to the normal release and need none.
```

## 7. Tests (same style as `tests/test_site_helpers.py` / `tests/test_http_app.py`)

Use a fake `NifeAPI` that records calls.

- Ownership: an id whose `appName` differs from `site_name` is rejected before any mutation.
- Preview vs confirm: each confirm-gated tool performs no mutation without `confirm=true`.
- `switch_site_blue_green`: unhealthy target refused; allowed with `allow_unhealthy`; wrong status refused.
- `complete_site_blue_green`: refused before a switch.
- Creation: refuses when a strategy is already active, unknown versions, identical versions, suspended
  site, out-of-range percentages; plan-limit errors are passed through.
- `scale_site_canary_traffic`: refused for A/B experiments; decreasing needs no confirm; large jump warns.
- `stop_site_experiment(outcome="abort")` without a reason is rejected.
- `get_release_details`: rows split by version; missing version reports no data instead of copying.
- Annotations: every tool in section 3 is registered with the annotation listed there.

## 8. Open questions (verify in the backend before building)

1. Do `service.SwitchBlueGreen`, `RollBackBlueGreen`, `CompleteBlueGreen`, `StartSiteExperiment`,
   `EndSiteExperiment`, `PromoteSiteExperiment` and `ScaleSiteCanary` check that `user.ID` owns the
   site? If not, that is an authorization bug independent of this connector.
2. `RecordS3Metric` and `CollectS3Metrics` show no ownership check on `appName`; confirm and fix.
3. Does `PrepareBlueGreen` / `PrepareExperiment` validate that versions exist and refuse a second
   concurrent strategy? The tools enforce both anyway, but the exact error text matters.
4. The exact status strings (`stopped`, `completed`, `switching`, ...) so the allow-lists are right.
5. Fix `getS3ExperimentMetrics` to filter by version, and either implement `autoPromote` or remove it
   from the schema defaults so the schema stops promising it.
