---
name: openshift-gitops
description: >
  Install, configure, fix, and troubleshoot the OpenShift GitOps (ArgoCD) operator on OpenShift.
  Use when working with ArgoCD Applications, ApplicationSets, AppProjects, sync policies, or the
  openshift-gitops-operator subscription. Covers OLM installation, ArgoCD CR configuration,
  app-of-apps patterns, RBAC, and declarative deployment for the outpatient-flow-analytics project.
compatibility: Requires OpenShift 4.14+ with cluster-admin access and oc CLI.
---

# OpenShift GitOps (ArgoCD) — Bootstrap & Troubleshoot

ArgoCD is the **foundation** of the outpatient-flow-analytics deployment pipeline.
This skill covers installing the operator (Step 0 of every bootstrap), then
diagnosing and fixing the issues you will hit once Applications start syncing.

## Bootstrap Workflow

ArgoCD must be running before anything else can be deployed declaratively.
The full bootstrap sequence is:

```
Step 0 ── Install ArgoCD operator (this skill's install.sh)
              │
Step 1 ── Apply the ocp-gpu-gitops big-bang app-of-apps
              │   oc apply -f https://raw.githubusercontent.com/samueltauil/ocp-gpu-gitops/\
              │     main/gitops/manifests/cluster/bootstrap/base/bigbang-app.yaml
              │
              ├─► NFD operator        (sync-wave 2)
              ├─► NVIDIA GPU operator (sync-wave 3)
              └─► DCGM dashboard      (sync-wave 4)
              │
Step 2 ── Apply the OpenShift Pipelines ArgoCD Application
              │   oc apply -f openshift/argocd/openshift-pipelines-app.yaml
              │
              └─► Pipelines operator  (sync-wave 5)
```

> **Key point:** If ArgoCD is unhealthy, *nothing else deploys*. Always fix
> ArgoCD first, then work on downstream Applications.

## When to use this skill

Use this skill when:
- **Installing** the OpenShift GitOps operator as Step 0 of a fresh cluster bootstrap
- **Troubleshooting** sync failures, drift, health degradation, or permission errors in any ArgoCD Application
- **Managing** the ocp-gpu-gitops app-of-apps or the Pipelines ArgoCD Application
- **Diagnosing** why an Application is stuck in Progressing, OutOfSync, Degraded, or Missing
- **Fixing** namespace labeling, RBAC, CRD-not-found, or TLS route issues
- Creating or editing Application, ApplicationSet, or AppProject CRs
- Configuring sync policies, RBAC, or SSO for ArgoCD

## Step 0: Install the ArgoCD Operator

> Run `bash .github/skills/openshift-gitops/scripts/install.sh` — it is
> idempotent and safe to re-run. The steps below describe what the script does.

### Create the Subscription

OpenShift GitOps is cluster-scoped. An ArgoCD instance is auto-created in `openshift-gitops`.

```yaml
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: openshift-gitops-operator
  namespace: openshift-operators
spec:
  channel: latest
  installPlanApproval: Automatic
  name: openshift-gitops-operator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
```

### Wait for the operator

```bash
oc get csv -n openshift-gitops -w
oc wait --for=condition=Available deployment/openshift-gitops-server \
  -n openshift-gitops --timeout=300s
```

### Get the ArgoCD route

```bash
oc get route openshift-gitops-server -n openshift-gitops -o jsonpath='{.spec.host}'
```

Admin password (if not using OpenShift SSO):
```bash
oc extract secret/openshift-gitops-cluster -n openshift-gitops --to=-
```

### Verify the installation

```bash
bash .github/skills/openshift-gitops/scripts/verify.sh
```

Returns exit 0 if healthy, non-zero with diagnostics if not.

## Troubleshooting

This is the primary focus of the skill. Sections are ordered from most common
to least common.

### Application stuck in "OutOfSync"

The most frequent issue. Resources on the cluster don't match Git.

```bash
# See what is out of sync
oc get application <app-name> -n openshift-gitops \
  -o jsonpath='{.status.resources[?(@.status!="Synced")]}' | python3 -m json.tool

# View the full sync status
oc get application <app-name> -n openshift-gitops \
  -o jsonpath='{.status.sync}' | python3 -m json.tool

# View the live-vs-desired diff
oc get application <app-name> -n openshift-gitops \
  -o jsonpath='{.status.resources}' | python3 -m json.tool

# Force a sync (resolves most transient drift)
oc -n openshift-gitops exec deploy/openshift-gitops-server -- \
  argocd app sync <app-name> --force

# Hard refresh (re-reads Git and recalculates diff)
oc -n openshift-gitops exec deploy/openshift-gitops-server -- \
  argocd app get <app-name> --hard-refresh
```

**Common causes:**
- Mutating webhooks or controllers adding fields ArgoCD doesn't expect.
  Fix: add `resourceExclusions` or `ignoreDifferences` in the ArgoCD CR.
- CRD status subresource changes. Fix: ArgoCD already ignores `.status` by default,
  but custom CRDs may need explicit `ignoreDifferences` entries.

### Application stuck in "Progressing"

The health check never reaches `Healthy`. Deployments, StatefulSets, or
operator CRs are not becoming ready.

```bash
# Check which resources are Progressing
oc get application <app-name> -n openshift-gitops \
  -o jsonpath='{.status.resources[?(@.health.status=="Progressing")]}' | python3 -m json.tool

# Check the health details
oc get application <app-name> -n openshift-gitops \
  -o jsonpath='{.status.health}' | python3 -m json.tool

# Look at the underlying resource
oc describe <kind>/<name> -n <namespace>
oc get events -n <namespace> --sort-by='.lastTimestamp' | tail -20
```

**Common causes:**
- Pod stuck in `ImagePullBackOff` — wrong image reference or missing pull secret.
- Pod stuck in `Pending` — insufficient resources or no nodes with matching
  tolerations/affinity (e.g., GPU nodes not yet labeled by NFD).
- Operator CR waiting on a dependency that hasn't installed yet — check
  sync-wave ordering.

### Application "Degraded" or "Missing"

```bash
# Check health details
oc get application <app-name> -n openshift-gitops \
  -o jsonpath='{.status.health}' | python3 -m json.tool

# Check conditions (most specific error messages are here)
oc get application <app-name> -n openshift-gitops \
  -o jsonpath='{.status.conditions}' | python3 -m json.tool
```

**Most common cause:** target namespace not labeled for ArgoCD management.

```bash
oc label namespace <target-ns> argocd.argoproj.io/managed-by=openshift-gitops
```

### Permission denied on sync

ArgoCD's application-controller needs RBAC for every resource type it manages.

```bash
# Check the controller logs for permission errors
oc logs -n openshift-gitops deploy/openshift-gitops-application-controller \
  --tail=50 | grep -i "forbidden\|error\|denied"

# Check which service account the controller uses
oc get argocd openshift-gitops -n openshift-gitops \
  -o jsonpath='{.spec.controller}' | python3 -m json.tool
```

**Fixes:**
- For **namespace-scoped** resources — label the target namespace:
  ```bash
  oc label namespace <ns> argocd.argoproj.io/managed-by=openshift-gitops
  ```
- For **cluster-scoped** resources (Subscriptions, CRDs, ClusterRoles) —
  update the AppProject's `clusterResourceWhitelist`:
  ```yaml
  spec:
    clusterResourceWhitelist:
      - group: '*'
        kind: '*'
  ```
- If the default `openshift-gitops` AppProject is too restrictive, check
  whether the Application's `spec.project` references a custom AppProject.

### Namespace labeling issues

ArgoCD refuses to manage resources in namespaces it doesn't own.

```bash
# List namespaces that ArgoCD manages
oc get namespaces -l argocd.argoproj.io/managed-by=openshift-gitops

# Label the project namespaces
oc label namespace edge-collector argocd.argoproj.io/managed-by=openshift-gitops
oc label namespace central-analytics argocd.argoproj.io/managed-by=openshift-gitops

# Verify the label
oc get namespace <ns> --show-labels | grep argocd
```

If the Application targets `openshift-operators` (e.g., the Pipelines
operator), that namespace does **not** need the label — it is cluster-scoped.

### Sync fails with "CRD not found"

When deploying operator CRs before the operator creates the CRD:

```yaml
# Add to the Application spec or kustomization.yaml:
syncOptions:
  - SkipDryRunOnMissingResource=true
  - Validate=false
```

Both the `bigbang-app.yaml` and `openshift-pipelines-app.yaml` already set
`SkipDryRunOnMissingResource=true`. If you create new Applications for
operator CRs, always include this option.

### Drift detection — selfHeal vs manual

Applications with `selfHeal: true` automatically revert manual changes on the
cluster. This is intentional for operator subscriptions and CRs. If you need
to temporarily override:

```bash
# Pause auto-sync on a specific Application
oc patch application <app-name> -n openshift-gitops --type merge \
  -p '{"spec":{"syncPolicy":{"automated":null}}}'

# Make your manual change...

# Re-enable auto-sync
oc patch application <app-name> -n openshift-gitops --type merge \
  -p '{"spec":{"syncPolicy":{"automated":{"selfHeal":true,"prune":false}}}}'
```

### ArgoCD server not accessible

```bash
# Check route
oc get route openshift-gitops-server -n openshift-gitops

# Check server pod
oc get pods -n openshift-gitops -l app.kubernetes.io/name=openshift-gitops-server

# Check TLS
oc get route openshift-gitops-server -n openshift-gitops \
  -o jsonpath='{.spec.tls.termination}'

# Restart the server if it's crash-looping
oc rollout restart deployment/openshift-gitops-server -n openshift-gitops
```

### Controller or repo-server issues

If Applications are not syncing at all, the controller or repo-server may be unhealthy.

```bash
# Check all pods in the openshift-gitops namespace
oc get pods -n openshift-gitops

# Controller logs (sync engine)
oc logs -n openshift-gitops deploy/openshift-gitops-application-controller \
  --tail=50

# Repo-server logs (Git clone + manifest generation)
oc logs -n openshift-gitops deploy/openshift-gitops-repo-server --tail=50

# Restart if needed
oc rollout restart deployment/openshift-gitops-application-controller -n openshift-gitops
oc rollout restart deployment/openshift-gitops-repo-server -n openshift-gitops
```

## Managing ArgoCD Applications

### The ocp-gpu-gitops app-of-apps

After Step 1 of the bootstrap, ArgoCD manages four Applications from the
[ocp-gpu-gitops](https://github.com/samueltauil/ocp-gpu-gitops) repo.

```bash
# List all Applications and their status
oc get applications -n openshift-gitops \
  -o custom-columns='NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status'

# Check a specific child app
oc get application nfd-operator -n openshift-gitops -o yaml
oc get application nvidia-gpu-operator -n openshift-gitops -o yaml

# Force sync a specific child app
oc -n openshift-gitops exec deploy/openshift-gitops-server -- \
  argocd app sync nfd-operator --force

# Force sync all child apps
for app in $(oc get applications -n openshift-gitops -o name); do
  oc -n openshift-gitops exec deploy/openshift-gitops-server -- \
    argocd app sync "$(basename "$app")" --force
done

# View the diff between Git and live state
oc -n openshift-gitops exec deploy/openshift-gitops-server -- \
  argocd app diff <app-name>
```

### The OpenShift Pipelines ArgoCD Application

Deployed from this repo at `openshift/argocd/openshift-pipelines-app.yaml`
(sync-wave 5, after GPU infrastructure).

```bash
# Apply the Pipelines Application
oc apply -f openshift/argocd/openshift-pipelines-app.yaml

# Check its status
oc get application openshift-pipelines-operator -n openshift-gitops \
  -o custom-columns='SYNC:.status.sync.status,HEALTH:.status.health.status'

# View conditions if unhealthy
oc get application openshift-pipelines-operator -n openshift-gitops \
  -o jsonpath='{.status.conditions}' | python3 -m json.tool
```

### Checking overall sync status

```bash
# Quick summary of every Application
oc get applications -n openshift-gitops \
  -o custom-columns='NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status,WAVE:.metadata.annotations.argocd\.argoproj\.io/sync-wave'

# Find all unhealthy or out-of-sync Applications
oc get applications -n openshift-gitops -o json | \
  python3 -c "
import json, sys
apps = json.load(sys.stdin)['items']
for a in apps:
    sync = a.get('status',{}).get('sync',{}).get('status','Unknown')
    health = a.get('status',{}).get('health',{}).get('status','Unknown')
    if sync != 'Synced' or health != 'Healthy':
        print(f\"{a['metadata']['name']:40s} sync={sync:12s} health={health}\")
"
```

## Looking up CRD field details

When you need to understand specific configuration fields, enum values, defaults, or nested structures, use the lookup script to query the full OpenAPI schemas in `openshift/crds/openshift-gitops-operator/`:

```bash
# List all available CRDs
bash .github/skills/openshift-gitops/scripts/lookup-crd.sh

# Show top-level spec fields for ArgoCD
bash .github/skills/openshift-gitops/scripts/lookup-crd.sh argocds

# Drill into nested fields
bash .github/skills/openshift-gitops/scripts/lookup-crd.sh argocds spec.server
bash .github/skills/openshift-gitops/scripts/lookup-crd.sh argocds spec.rbac
bash .github/skills/openshift-gitops/scripts/lookup-crd.sh applications spec.syncPolicy
```

See [references/crd-summary.md](references/crd-summary.md) for a quick overview of all fields.

## Key CRDs

Full schemas are in `openshift/crds/openshift-gitops-operator/`. Key CRDs:

| CRD | Purpose |
|-----|---------|
| `ArgoCD` | Defines an ArgoCD instance (server, repo-server, controller, etc.) |
| `Application` | Declares a desired state to sync from Git → cluster |
| `ApplicationSet` | Generates multiple Applications from templates + generators |
| `AppProject` | RBAC boundary — restricts sources, destinations, resources |
| `RolloutManager` | Manages Argo Rollouts for progressive delivery |
| `Rollout` | Blue-green or canary deployment strategy |
| `AnalysisTemplate` | Defines metrics to evaluate during rollouts |
| `NotificationsConfiguration` | Configures alerts (Slack, email, webhook) |
| `ImageUpdater` | Auto-updates container image tags from registries |
| `GitOpsService` | OpenShift-specific GitOps service configuration |

See [references/crd-summary.md](references/crd-summary.md) for field-level details.

## Configuration

### ArgoCD instance — typical production settings

```yaml
apiVersion: argoproj.io/v1beta1
kind: ArgoCD
metadata:
  name: openshift-gitops
  namespace: openshift-gitops
spec:
  server:
    route:
      enabled: true
      tls:
        termination: reencrypt
  controller:
    resources:
      requests:
        cpu: 250m
        memory: 512Mi
      limits:
        cpu: "2"
        memory: 2Gi
  repo:
    resources:
      requests:
        cpu: 250m
        memory: 256Mi
  resourceExclusions: |
    - apiGroups:
        - tekton.dev
      kinds:
        - TaskRun
        - PipelineRun
  ha:
    enabled: false
  rbac:
    defaultPolicy: role:readonly
    policy: |
      g, system:cluster-admins, role:admin
      g, cluster-admins, role:admin
    scopes: '[groups]'
```

### Grant ArgoCD namespace management

ArgoCD needs permissions to manage resources in target namespaces:

```bash
# For each target namespace
oc label namespace edge-collector argocd.argoproj.io/managed-by=openshift-gitops
oc label namespace central-analytics argocd.argoproj.io/managed-by=openshift-gitops
```

## App-of-Apps Pattern

The [ocp-gpu-gitops](https://github.com/samueltauil/ocp-gpu-gitops) repo uses
an app-of-apps pattern to bootstrap NFD + GPU operator + DCGM dashboard with a
single `oc apply`. Sync waves control ordering.

### Bootstrap Application (the "big bang")

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: app-of-apps
  namespace: openshift-gitops
  annotations:
    argocd.argoproj.io/sync-wave: "1"
    argocd.argoproj.io/compare-options: IgnoreExtraneous
spec:
  destination:
    namespace: openshift-gitops
    server: https://kubernetes.default.svc
  project: default
  source:
    path: gitops/manifests/cluster/apps/base
    repoURL: https://github.com/samueltauil/ocp-gpu-gitops.git
    targetRevision: main
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
```

### Sync wave ordering

Use `argocd.argoproj.io/sync-wave` annotations to control the order:

| Wave | Component | Source |
|------|-----------|--------|
| 1 | app-of-apps | ocp-gpu-gitops |
| 2 | NFD operator | ocp-gpu-gitops |
| 3 | NVIDIA GPU operator | ocp-gpu-gitops |
| 4 | DCGM dashboard | ocp-gpu-gitops |
| 5 | OpenShift Pipelines operator | this repo (`openshift/argocd/openshift-pipelines-app.yaml`) |

### Handling CRDs that don't exist yet

When deploying operators via GitOps, CRD instances (e.g., ClusterPolicy, NodeFeatureDiscovery) may reference CRDs that don't exist until the operator installs. Use:

```yaml
metadata:
  annotations:
    argocd.argoproj.io/sync-options: SkipDryRunOnMissingResource=true
```

This is applied via kustomize `commonAnnotations` in aggregate overlays.

## Verification checklist

```bash
bash .github/skills/openshift-gitops/scripts/verify.sh
```

Or manually:

```bash
echo "=== Subscription ==="
oc get sub openshift-gitops-operator -n openshift-operators -o jsonpath='{.status.currentCSV}'

echo "=== CSV Phase ==="
oc get csv -n openshift-gitops -o jsonpath='{.items[0].status.phase}'

echo "=== ArgoCD Instance ==="
oc get argocd -n openshift-gitops -o jsonpath='{.items[0].metadata.name}'

echo "=== Server Pod ==="
oc get pods -n openshift-gitops -l app.kubernetes.io/name=openshift-gitops-server --no-headers

echo "=== Route ==="
oc get route openshift-gitops-server -n openshift-gitops -o jsonpath='{.spec.host}'

echo "=== Applications ==="
oc get applications -n openshift-gitops --no-headers

echo "=== Sync Status ==="
oc get applications -n openshift-gitops -o custom-columns='NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status'
```

## Uninstallation

```bash
# Delete all Applications first
oc delete applications --all -n openshift-gitops

# Delete ArgoCD instance
oc delete argocd openshift-gitops -n openshift-gitops

# Delete Subscription
oc delete sub openshift-gitops-operator -n openshift-operators

# Delete CSV
oc delete csv -n openshift-gitops $(oc get csv -n openshift-gitops -o name)

# Remove namespace labels
oc label namespace edge-collector argocd.argoproj.io/managed-by-
oc label namespace central-analytics argocd.argoproj.io/managed-by-
```
