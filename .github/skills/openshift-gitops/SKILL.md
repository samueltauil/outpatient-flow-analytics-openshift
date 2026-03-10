---
name: openshift-gitops
description: >
  Install, configure, fix, and troubleshoot the OpenShift GitOps (ArgoCD) operator on OpenShift.
  Use when working with ArgoCD Applications, ApplicationSets, AppProjects, sync policies, or the
  openshift-gitops-operator subscription. Covers OLM installation, ArgoCD CR configuration,
  app-of-apps patterns, RBAC, and declarative deployment for the outpatient-flow-analytics project.
compatibility: Requires OpenShift 4.14+ with cluster-admin access and oc CLI.
---

# OpenShift GitOps (ArgoCD) Operator

## When to use this skill

Use this skill when:
- Installing or upgrading the OpenShift GitOps operator
- Creating or managing ArgoCD Application, ApplicationSet, or AppProject CRs
- Setting up app-of-apps patterns for multi-component deployments
- Configuring sync policies, RBAC, or SSO for ArgoCD
- Troubleshooting sync failures, drift, health issues, or permission errors
- Converting imperative deployments to declarative GitOps
- Bootstrapping GPU infrastructure via GitOps (NFD + GPU operator)

## Installation

### Step 1 — Create the Subscription

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

### Step 2 — Wait for the operator

```bash
oc get csv -n openshift-gitops -w
oc wait --for=condition=Available deployment/openshift-gitops-server \
  -n openshift-gitops --timeout=300s
```

### Step 3 — Get the ArgoCD route

```bash
oc get route openshift-gitops-server -n openshift-gitops -o jsonpath='{.spec.host}'
```

Admin password (if not using OpenShift SSO):
```bash
oc extract secret/openshift-gitops-cluster -n openshift-gitops --to=-
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

This pattern (used by [ocp-gpu-gitops](https://github.com/samueltauil/ocp-gpu-gitops)) bootstraps multiple components with a single apply. Sync waves control ordering.

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

| Wave | Component | Purpose |
|------|-----------|---------|
| 1 | app-of-apps | Bootstrap entry point |
| 2 | NFD operator | Must discover GPU nodes first |
| 3 | NVIDIA GPU operator | Needs NFD labels present |
| 4 | DCGM dashboard | Needs GPU operator metrics |

### Handling CRDs that don't exist yet

When deploying operators via GitOps, CRD instances (e.g., ClusterPolicy, NodeFeatureDiscovery) may reference CRDs that don't exist until the operator installs. Use:

```yaml
metadata:
  annotations:
    argocd.argoproj.io/sync-options: SkipDryRunOnMissingResource=true
```

This is applied via kustomize `commonAnnotations` in aggregate overlays.

## Project-Specific Setup (outpatient-flow-analytics)

### Application CR for this project

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: outpatient-flow-analytics
  namespace: openshift-gitops
spec:
  project: default
  source:
    repoURL: <your-repo-url>
    path: openshift/
    targetRevision: main
  destination:
    server: https://kubernetes.default.svc
    namespace: central-analytics
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

### GPU infrastructure via GitOps

Bootstrap NFD + GPU operator + DCGM dashboard with one command:

```bash
oc apply -f https://raw.githubusercontent.com/samueltauil/ocp-gpu-gitops/main/gitops/manifests/cluster/bootstrap/base/bigbang-app.yaml
```

This creates an app-of-apps that installs NFD (wave 2) → GPU operator (wave 3) → DCGM dashboard (wave 4).

## Troubleshooting

### Application stuck in "OutOfSync"

```bash
# Check sync status details
oc get application <app-name> -n openshift-gitops -o jsonpath='{.status.sync}' | python3 -m json.tool

# Check which resources differ
oc get application <app-name> -n openshift-gitops -o jsonpath='{.status.resources[?(@.status!="Synced")]}' | python3 -m json.tool

# Force sync
oc -n openshift-gitops exec deploy/openshift-gitops-server -- argocd app sync <app-name> --force
```

### Application "Degraded" or "Missing"

```bash
# Check health details
oc get application <app-name> -n openshift-gitops -o jsonpath='{.status.health}' | python3 -m json.tool

# Check conditions
oc get application <app-name> -n openshift-gitops -o jsonpath='{.status.conditions}' | python3 -m json.tool

# Common cause: target namespace not labeled for ArgoCD management
oc label namespace <target-ns> argocd.argoproj.io/managed-by=openshift-gitops
```

### Permission denied on sync

```bash
# ArgoCD controller needs ClusterRole for the target resources
# Check the controller logs
oc logs -n openshift-gitops deploy/openshift-gitops-application-controller --tail=30 | grep -i error

# For cluster-scoped resources, update the ArgoCD CR:
# spec.server.insecure or the AppProject's clusterResourceWhitelist
```

### Sync fails with "CRD not found"

When deploying operator CRs before the operator creates the CRD:

```yaml
# Add to the kustomization.yaml or Application sync options:
syncOptions:
  - SkipDryRunOnMissingResource=true
  - Validate=false
```

### ArgoCD server not accessible

```bash
# Check route
oc get route openshift-gitops-server -n openshift-gitops

# Check server pod
oc get pods -n openshift-gitops -l app.kubernetes.io/name=openshift-gitops-server

# Check TLS
oc get route openshift-gitops-server -n openshift-gitops -o jsonpath='{.spec.tls.termination}'
```

## Verification checklist

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
