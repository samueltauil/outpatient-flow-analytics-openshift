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
- Installing or upgrading the OpenShift Pipelines operator
- Creating or debugging Tekton Tasks, Pipelines, PipelineRuns, or TaskRuns
- Configuring TektonConfig, TektonChain, TektonResult, or TektonAddon CRs
- Troubleshooting pipeline failures, stuck pods, SCC issues, or GPU task scheduling
- Setting up CI/CD for the outpatient-flow-analytics project (3-stage pipeline)

## Installation

### Step 1 — Create the Subscription

The operator is cluster-scoped. No namespace or OperatorGroup creation is needed — OLM handles it in `openshift-operators`.

```yaml
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: openshift-pipelines-operator-rh
  namespace: openshift-operators
spec:
  channel: latest
  installPlanApproval: Automatic
  name: openshift-pipelines-operator-rh
  source: redhat-operators
  sourceNamespace: openshift-marketplace
```

```bash
oc apply -f - <<EOF
<paste above YAML>
EOF
```

### Step 2 — Wait for the operator to be ready

```bash
# Wait for CSV
oc get csv -n openshift-pipelines -w

# Wait for TektonConfig (auto-created by operator)
oc wait --for=condition=Ready tektonconfig/config --timeout=300s
```

### Step 3 — Verify

```bash
oc get tektonconfig config -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
# Expected: "True"

oc get pods -n openshift-pipelines -l app=tekton-pipelines-controller
# Expected: Running
```

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

### Critical: SCC grant for GPU tasks

The GPU analytics task uses NVIDIA RAPIDS images (UID 1001). Standard restricted SCC blocks this.

```bash
oc adm policy add-scc-to-user nonroot-v2 -z pipeline-sa -n central-analytics
```

### Critical: computeResources vs resources

**In Tekton v1 API, step resource requirements MUST use `computeResources`, NOT `resources`.** The `resources` field is silently ignored and LimitRange defaults apply instead.

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

### GPU task scheduling

The PipelineRun must set podTemplate for the GPU task:

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

## Troubleshooting

### Pipeline pod stuck in Pending

```bash
# Check events
oc get events -n central-analytics --sort-by='.lastTimestamp' | grep -i pipeline | tail -10

# Check pod description for scheduling issues
oc describe pod <pod-name> -n central-analytics | grep -A10 Events

# Common causes:
# - Missing SCC grant → "unable to validate against any security context constraint"
# - Missing GPU toleration → "node(s) had taint nvidia.com/gpu:NoSchedule"
# - ResourceQuota exceeded → check: oc describe resourcequota -n central-analytics
```

### TaskRun fails with permission denied

```bash
# Check which SCC the pod got
oc get pod <pod-name> -n central-analytics -o jsonpath='{.metadata.annotations.openshift\.io/scc}'

# If it shows "restricted" or "restricted-v2" for a RAPIDS task, fix with:
oc adm policy add-scc-to-user nonroot-v2 -z pipeline-sa -n central-analytics
```

### Task gets wrong resource limits (LimitRange applied)

This means `resources:` was used instead of `computeResources:` in the Task step. The fix is to change the YAML. Check with:

```bash
oc get tasks -n central-analytics -o yaml | grep -B2 -A5 "resources:"
# If you see resources: under steps, change to computeResources:
```

### TektonConfig not becoming Ready

```bash
oc get tektonconfig config -o yaml | grep -A20 "status:"
oc get pods -n openshift-pipelines --no-headers | grep -v Running
oc logs -n openshift-pipelines -l app=tekton-pipelines-controller --tail=50
```

### Cross-namespace access fails (ETL → edge DB)

The ETL and Tekton tasks in `central-analytics` need to reach PostgreSQL in `edge-collector`. Check:

```bash
# NetworkPolicy must allow cross-namespace traffic
oc get networkpolicy -n edge-collector -o yaml | grep -A10 "namespaceSelector"

# Secrets must exist
oc get secret edge-db-remote-credentials -n central-analytics
oc get secret central-db-credentials -n central-analytics
```

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
