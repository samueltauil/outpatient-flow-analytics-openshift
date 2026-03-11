---
name: openshift-pipelines
description: >
  Install, configure, fix, and troubleshoot the OpenShift Pipelines (Tekton) operator on OpenShift.
  Use when working with Tekton pipelines, tasks, triggers, chains, or the openshift-pipelines-operator-rh
  subscription. Covers OLM installation, TektonConfig CR, RBAC, SCC grants, GPU task scheduling, and
  CI/CD pipeline orchestration for the outpatient-flow-analytics project.
compatibility: Requires OpenShift 4.14+ with cluster-admin access and oc CLI.
---

# OpenShift Pipelines (Tekton) Operator

## When to use this skill

Use this skill when:
- Troubleshooting pipeline failures, stuck pods, SCC issues, or GPU task scheduling
- Diagnosing TektonConfig readiness problems or operator health
- Debugging `computeResources` vs `resources` issues in Tekton v1 Tasks
- Fixing SCC grants for RAPIDS/GPU workloads (nonroot-v2 for pipeline-sa)
- Installing or upgrading the OpenShift Pipelines operator
- Creating or debugging Tekton Tasks, Pipelines, PipelineRuns, or TaskRuns
- Setting up CI/CD for the outpatient-flow-analytics project (3-stage pipeline)

## First step — Run diagnostics

Before investigating any issue, run the verification script:

```bash
bash .github/skills/openshift-pipelines/scripts/verify.sh
```

This checks Subscription, CSV, TektonConfig readiness, controller pods, CRDs, and project-specific SCC grants. Exit code 0 means healthy; non-zero prints diagnostics showing exactly what failed.

## Installation

OpenShift Pipelines can be installed two ways. The GitOps method is preferred because it keeps the cluster state declarative and self-healing.

### Primary — GitOps via ArgoCD

> **Prerequisite:** OpenShift GitOps (ArgoCD) must already be running. See the [openshift-gitops skill](../.github/skills/openshift-gitops/) or install it first (Step 0 in the operator dependency order).

The ArgoCD Application manifest lives at `openshift/argocd/openshift-pipelines-app.yaml`. It points to `openshift/operators/openshift-pipelines/` which contains the OLM Subscription via Kustomize.

```bash
oc apply -f openshift/argocd/openshift-pipelines-app.yaml
```

ArgoCD will create the Subscription in `openshift-operators`, OLM installs the operator, and the operator auto-creates the `TektonConfig/config` CR. With `selfHeal: true`, ArgoCD will restore the Subscription if it is accidentally deleted.

Wait for the operator to become ready:

```bash
oc wait --for=condition=Ready tektonconfig/config --timeout=300s
```

Verify sync status in ArgoCD:

```bash
oc get application openshift-pipelines-operator -n openshift-gitops \
  -o jsonpath='{.status.sync.status}{"\n"}{.status.health.status}{"\n"}'
# Expected: Synced / Healthy
```

### Fallback — Direct install via script

If ArgoCD is not available, use the install script. It applies the same Subscription directly:

```bash
bash .github/skills/openshift-pipelines/scripts/install.sh
```

Then wait for readiness:

```bash
oc wait --for=condition=Ready tektonconfig/config --timeout=300s
```

### Post-install verification

```bash
oc get tektonconfig config -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
# Expected: "True"

oc get pods -n openshift-pipelines -l app=tekton-pipelines-controller
# Expected: Running
```

## Looking up CRD field details

When you need to understand specific configuration fields, enum values, defaults, or nested structures, use the lookup script to query the full OpenAPI schemas in `openshift/crds/openshift-pipelines-operator-rh/`:

```bash
# List all available CRDs
bash .github/skills/openshift-pipelines/scripts/lookup-crd.sh

# Show top-level spec fields for TektonConfig
bash .github/skills/openshift-pipelines/scripts/lookup-crd.sh tektonconfigs

# Drill into nested fields
bash .github/skills/openshift-pipelines/scripts/lookup-crd.sh tektonconfigs spec.pipeline
bash .github/skills/openshift-pipelines/scripts/lookup-crd.sh tektonchains spec.artifacts
```

See [references/crd-summary.md](references/crd-summary.md) for a quick overview of all fields.

## Key CRDs

Full schemas are in `openshift/crds/openshift-pipelines-operator-rh/`. Key CRDs:

| CRD | Purpose |
|-----|---------|
| `TektonConfig` | Master config — controls all sub-components (auto-created as `config`) |
| `TektonPipeline` | Pipeline controller settings |
| `TektonTrigger` | Event-driven trigger controller |
| `TektonChain` | Supply-chain security (signing, provenance) |
| `TektonAddon` | Cluster tasks, pipeline templates |
| `TektonResult` | Results storage backend (logs/records) |
| `TektonHub` | Task catalog hub |
| `TektonPruner` | Auto-pruning old PipelineRuns/TaskRuns |
| `ManualApprovalGate` | Manual approval steps in pipelines |
| `OpenShiftPipelinesAsCode` | Pipelines-as-Code (GitHub/GitLab integration) |

See [references/crd-summary.md](references/crd-summary.md) for field-level details.

## Troubleshooting

> **Start here:** Always run `bash .github/skills/openshift-pipelines/scripts/verify.sh` first. It catches the most common issues automatically.

### TektonConfig not reaching Ready state

The operator auto-creates `TektonConfig/config`. If it stays not-Ready:

```bash
# Check all status conditions (not just Ready)
oc get tektonconfig config -o jsonpath='{range .status.conditions[*]}{.type}: {.status} — {.message}{"\n"}{end}'

# Look for pods that are not Running in the operator namespace
oc get pods -n openshift-pipelines --no-headers | grep -v Running

# Check controller logs for errors
oc logs -n openshift-pipelines -l app=tekton-pipelines-controller --tail=50

# Check if the CSV is stuck
oc get csv -n openshift-pipelines -o jsonpath='{.items[0].status.phase}'
# Expected: "Succeeded" — if "InstallReady" or "Pending", OLM is still working

# If using GitOps install, also check ArgoCD sync status
oc get application openshift-pipelines-operator -n openshift-gitops -o jsonpath='{.status.conditions}'
```

Common causes:
- OLM catalog source is unhealthy → `oc get catalogsource -n openshift-marketplace`
- An older CSV is blocking upgrade → delete the stuck CSV and let OLM recreate
- Webhook timeout → restart the webhook pod in `openshift-pipelines`

### SCC configuration for RAPIDS/GPU tasks

The GPU analytics task uses NVIDIA RAPIDS images that run as **UID 1001**. The default `restricted-v2` SCC blocks this UID. The `pipeline-sa` ServiceAccount needs `nonroot-v2` SCC in `central-analytics`.

**Diagnose:**

```bash
# Check which SCC a task pod actually received
oc get pod <pod-name> -n central-analytics -o jsonpath='{.metadata.annotations.openshift\.io/scc}'
# If it shows "restricted" or "restricted-v2", the SCC grant is missing

# Check if the grant exists
oc adm policy who-can use scc nonroot-v2 | grep pipeline-sa
```

**Fix:**

```bash
oc adm policy add-scc-to-user nonroot-v2 -z pipeline-sa -n central-analytics
```

**Verify:**

```bash
# Rerun a TaskRun and confirm the pod gets nonroot-v2
oc get pod <new-pod-name> -n central-analytics -o jsonpath='{.metadata.annotations.openshift\.io/scc}'
# Expected: nonroot-v2
```

### CRITICAL: computeResources vs resources in Tekton v1 API

**In Tekton v1 API, step resource requirements MUST use `computeResources`, NOT `resources`.** The `resources` field is **silently ignored** — no error, no warning — and LimitRange defaults are applied instead. This is the #1 cause of GPU tasks failing to request GPU devices.

```yaml
# WRONG — silently ignored in Tekton v1
steps:
  - name: analytics
    resources:
      requests:
        nvidia.com/gpu: "1"

# CORRECT
steps:
  - name: analytics
    computeResources:
      requests:
        nvidia.com/gpu: "1"
        memory: "8Gi"
        cpu: "2"
      limits:
        nvidia.com/gpu: "1"
        memory: "32Gi"
        cpu: "8"
```

**Diagnose:** If a GPU task runs but gets no GPU, check the Task YAML:

```bash
# Find tasks using the wrong field name
oc get tasks -n central-analytics -o yaml | grep -B2 -A5 "resources:"
# If you see resources: under steps (not computeResources:), that is the bug
```

### Pipeline/TaskRun failures — debugging stuck or failed runs

**Pipeline pod stuck in Pending:**

```bash
# Check events for scheduling failures
oc get events -n central-analytics --sort-by='.lastTimestamp' | grep -i pipeline | tail -10

# Inspect the pod for details
oc describe pod <pod-name> -n central-analytics | grep -A10 Events

# Common causes:
# - Missing SCC grant → "unable to validate against any security context constraint"
# - Missing GPU toleration → "node(s) had taint nvidia.com/gpu:NoSchedule"
# - ResourceQuota exceeded → oc describe resourcequota -n central-analytics
# - No GPU nodes available → oc get nodes -l nvidia.com/gpu.present=true
```

**TaskRun times out:**

```bash
# Check the pipeline and task timeout settings
oc get tektonconfig config -o jsonpath='{.spec.pipeline.default-timeout-minutes}'

# Override timeout on a specific PipelineRun
# Add spec.timeouts.pipeline: "2h0m0s" to the PipelineRun YAML
```

**PipelineRun stuck in Running (but tasks completed):**

```bash
# Check for finally tasks or approval gates that haven't completed
oc get pipelinerun <name> -n central-analytics -o jsonpath='{.status.childReferences[*].name}'

# Check individual TaskRun statuses
oc get taskruns -n central-analytics -l tekton.dev/pipelineRun=<name> \
  -o custom-columns='NAME:.metadata.name,STATUS:.status.conditions[0].reason'
```

### GPU task scheduling

The PipelineRun must set podTemplate for GPU tasks to land on GPU nodes:

```yaml
taskRunSpecs:
  - pipelineTaskName: gpu-analytics
    podTemplate:
      nodeSelector:
        nvidia.com/gpu.present: "true"
      tolerations:
        - key: nvidia.com/gpu
          operator: Exists
          effect: NoSchedule
      securityContext:
        runAsNonRoot: true
        runAsUser: 1001
        runAsGroup: 1001
        fsGroup: 1001
```

**Diagnose scheduling failures:**

```bash
# Verify GPU nodes exist and are ready
oc get nodes -l nvidia.com/gpu.present=true -o wide

# Check if GPUs are available (not fully allocated)
oc describe node <gpu-node> | grep -A5 "Allocated resources" | grep nvidia

# Check taints on GPU nodes
oc get nodes -l nvidia.com/gpu.present=true -o jsonpath='{range .items[*]}{.metadata.name}: {.spec.taints}{"\n"}{end}'
```

### Cross-namespace access (ETL → edge-collector PostgreSQL)

The ETL and Tekton tasks in `central-analytics` need to reach PostgreSQL in `edge-collector`:

```bash
# NetworkPolicy must allow cross-namespace traffic
oc get networkpolicy -n edge-collector -o yaml | grep -A10 "namespaceSelector"

# Secrets must exist in central-analytics
oc get secret edge-db-remote-credentials -n central-analytics
oc get secret central-db-credentials -n central-analytics

# Test connectivity from central-analytics
oc run pg-test --rm -it --image=registry.redhat.io/rhel9/postgresql-15 \
  -n central-analytics --restart=Never -- \
  pg_isready -h edge-db.edge-collector.svc.cluster.local -p 5432
```

## Configuration

### TektonConfig — typical production settings

```yaml
apiVersion: operator.tekton.dev/v1alpha1
kind: TektonConfig
metadata:
  name: config
spec:
  profile: all                    # all | lite | basic
  targetNamespace: openshift-pipelines
  pruner:
    keep: 100
    schedule: "0 8 * * *"
    resources:
      - pipelinerun
      - taskrun
  pipeline:
    default-timeout-minutes: "60"
    enable-api-fields: beta
  chain:
    disabled: false
  addon: {}
  trigger: {}
```

### Enabling Pipelines-as-Code

```yaml
apiVersion: operator.tekton.dev/v1alpha1
kind: TektonConfig
metadata:
  name: config
spec:
  platforms:
    openshift:
      pipelinesAsCode:
        enable: true
        settings:
          application-name: "Pipelines as Code CI"
```

## Project-Specific Setup (outpatient-flow-analytics)

This project runs a 3-stage Tekton pipeline for surgical analytics. Files are in `openshift/tekton/`.

### Apply order

```bash
oc apply -f openshift/tekton/04-rbac.yaml        # ServiceAccount + RBAC
oc apply -f openshift/tekton/01-tasks.yaml        # 3 Tasks
oc apply -f openshift/tekton/03-pipeline.yaml     # Pipeline definition
oc apply -f openshift/tekton/05-pipelinerun.yaml  # Trigger a run (optional)
```

After applying, ensure you have completed the SCC grant and verified `computeResources` usage — see [SCC configuration](#scc-configuration-for-rapidsgpu-tasks) and [computeResources vs resources](#critical-computeresources-vs-resources-in-tekton-v1-api) in the Troubleshooting section above.

## Verification checklist

Run these commands to confirm a healthy Pipelines installation:

```bash
echo "=== Subscription ==="
oc get sub openshift-pipelines-operator-rh -n openshift-operators -o jsonpath='{.status.currentCSV}'

echo "=== CSV Phase ==="
oc get csv -n openshift-pipelines -o jsonpath='{.items[0].status.phase}'

echo "=== TektonConfig ==="
oc get tektonconfig config -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'

echo "=== Controller Pods ==="
oc get pods -n openshift-pipelines -l app=tekton-pipelines-controller --no-headers

echo "=== CRDs ==="
oc get crd pipelines.tekton.dev tasks.tekton.dev pipelineruns.tekton.dev --no-headers

echo "=== Version ==="
oc get tektonconfig config -o jsonpath='{.status.version}'
```

## Uninstallation

```bash
# Delete TektonConfig first
oc delete tektonconfig config

# Delete Subscription
oc delete subscription openshift-pipelines-operator-rh -n openshift-operators

# Delete CSV
oc delete csv -n openshift-pipelines $(oc get csv -n openshift-pipelines -o name)

# CRDs are retained by default — delete manually if needed
oc get crd | grep tekton | awk '{print $1}' | xargs oc delete crd
```
