---
name: nfd
description: >
  Install, configure, fix, and troubleshoot the Node Feature Discovery (NFD) operator on OpenShift.
  Use when working with hardware detection, node labeling, GPU node discovery, NodeFeatureDiscovery
  CR, NodeFeatureRule, or the nfd subscription. Covers OLM installation, worker configuration for
  NVIDIA GPU detection (PCI class 03/12, vendor 10de), and node scheduling labels used by
  the outpatient-flow-analytics project.
compatibility: Requires OpenShift 4.14+ with cluster-admin access and oc CLI.
---

# Node Feature Discovery (NFD) Operator

## When to use this skill

Use this skill when:
- Diagnosing missing GPU node labels (`feature.node.kubernetes.io/pci-10de.present=true`)
- Troubleshooting NFD worker pods not running or in CrashLoopBackOff
- Investigating GPU node detection failures (PCI class configuration)
- Debugging RBAC/permission issues with NodeFeature or NodeFeatureRule resources
- Tuning worker config (sleep interval, PCI device filters)
- Creating custom NodeFeatureRules for advanced label logic
- Preparing nodes for the NVIDIA GPU Operator (NFD is a prerequisite)

## How NFD is installed

**Primary (GitOps):** NFD is installed automatically via the
[ocp-gpu-gitops](https://github.com/samueltauil/ocp-gpu-gitops) ArgoCD
app-of-apps pattern at **sync-wave 2**. Apply the bootstrap to get NFD (and the
GPU operator) installed declaratively:

```bash
oc apply -f https://raw.githubusercontent.com/samueltauil/ocp-gpu-gitops/main/gitops/manifests/cluster/bootstrap/base/bigbang-app.yaml
```

**Fallback (direct install):** For clusters without GitOps, use the bundled
install script. It is idempotent and safe to re-run:

```bash
bash .github/skills/nfd/scripts/install.sh          # stable channel, default image
bash .github/skills/nfd/scripts/install.sh stable <custom-image>  # override image
```

See [Fallback: Direct Installation](#fallback-direct-installation) for the full
manual procedure.

## First step: run verify.sh

**Always start here.** The verification script checks every layer of the NFD
stack and exits non-zero with diagnostics on failure:

```bash
bash .github/skills/nfd/scripts/verify.sh
```

It validates:
1. NFD Subscription and CSV phase (`Succeeded`)
2. NodeFeatureDiscovery CR exists
3. NFD master pods running (count > 0)
4. NFD worker pods running (count > 0)
5. GPU node detection — nodes with `feature.node.kubernetes.io/pci-10de.present=true`

A passing run prints ✓ for each check. Any ✗ tells you exactly where to focus.

## Troubleshooting

### Missing GPU labels (`pci-10de.present`)

Nodes with NVIDIA GPUs should carry `feature.node.kubernetes.io/pci-10de.present=true`.
If the label is missing:

```bash
# 1. Confirm NFD workers are running on the GPU node
oc get pods -n openshift-nfd -l app=nfd-worker -o wide

# 2. Inspect the NodeFeature object for that node
oc get nodefeature -n openshift-nfd
oc get nodefeature <node-name> -n openshift-nfd -o yaml | grep -A20 "pci"

# 3. Verify the PCI device class whitelist includes GPU classes
oc get nodefeaturediscovery nfd-instance -n openshift-nfd -o yaml \
  | grep -A10 "deviceClassWhitelist"
```

**Required PCI classes for NVIDIA GPUs:**
- `03` — Display controller (consumer and data-center GPUs)
- `12` — Processing accelerator (compute GPUs like H100, A100)

**Required deviceLabelFields:**
- `vendor` — produces the `pci-10de` label from NVIDIA's PCI vendor ID

If the whitelist or label fields are wrong, patch the CR or update the GitOps
manifests and resync.

After fixing config, restart workers to pick up changes immediately:

```bash
oc delete pods -n openshift-nfd -l app=nfd-worker
```

### NFD worker pods not running or CrashLoopBackOff

```bash
# Check pod status
oc get pods -n openshift-nfd -l app=nfd-worker

# Read worker logs
oc logs -n openshift-nfd -l app=nfd-worker --tail=50
```

Common causes:
| Symptom | Cause | Fix |
|---------|-------|-----|
| `CrashLoopBackOff` | Invalid `workerConfig` YAML | Check syntax in NodeFeatureDiscovery CR |
| `ImagePullBackOff` | Wrong image ref or missing pull secret | Verify image and `imagePullPolicy` |
| `0/N` workers | No worker DaemonSet created | Check NFD master logs and CR status |
| Workers only on some nodes | Taints preventing scheduling | Add matching tolerations in CR |

### RBAC / permission issues

NFD master and worker service accounts need ClusterRoles to read/write
NodeFeature and NodeFeatureRule resources. Symptoms of missing RBAC:

- Worker logs show `Forbidden` or `cannot create resource "nodefeatures"`
- Master logs show `cannot list resource "nodefeaturerules"`

Verify the required bindings exist:

```bash
oc get clusterrolebinding | grep nfd
# Expected:
#   nfd-master-nodefeature-access
#   nfd-master-nodefeaturerules-access
#   nfd-worker-nodefeature-write-access
```

If missing, the GitOps manifests should recreate them on sync. For manual
clusters, apply the RBAC from [Fallback: Direct Installation](#fallback-direct-installation)
or re-run `install.sh`.

### NodeFeatureDiscovery CR not reconciling

```bash
# Check operator controller logs
oc logs -n openshift-nfd deploy/nfd-controller-manager --tail=50

# Check CR status
oc get nodefeaturediscovery nfd-instance -n openshift-nfd -o yaml | grep -A10 "status:"
```

### Labels present but GPU operator not using them

The GPU operator looks for `feature.node.kubernetes.io/pci-10de.present=true`.
Verify the label exists:

```bash
oc get nodes -l feature.node.kubernetes.io/pci-10de.present=true -o name
```

If empty but GPUs are physically present:
1. Ensure PCI classes `03` and `12` are in the whitelist
2. Ensure `vendor` is in `deviceLabelFields`
3. Restart NFD workers: `oc delete pods -n openshift-nfd -l app=nfd-worker`

### Worker config changes not taking effect

NFD workers read their config from the NodeFeatureDiscovery CR. After changing
`workerConfig`, workers must be restarted:

```bash
# Edit the CR (or update GitOps manifests and sync)
oc edit nodefeaturediscovery nfd-instance -n openshift-nfd

# Then restart workers
oc delete pods -n openshift-nfd -l app=nfd-worker

# Verify new config is active (check sleep interval in logs)
oc logs -n openshift-nfd -l app=nfd-worker --tail=10 | grep -i "sleep\|interval"
```

## Looking up CRD field details

When you need to understand specific configuration fields, enum values, defaults, or nested structures, use the lookup script to query the full OpenAPI schemas in `openshift/crds/nfd/`:

```bash
# List all available CRDs
bash .github/skills/nfd/scripts/lookup-crd.sh

# Show top-level spec fields for NodeFeatureDiscovery
bash .github/skills/nfd/scripts/lookup-crd.sh nodefeaturediscoveries

# Drill into nested fields
bash .github/skills/nfd/scripts/lookup-crd.sh nodefeaturediscoveries spec.workerConfig
bash .github/skills/nfd/scripts/lookup-crd.sh nodefeaturerules spec.rules
```

See [references/crd-summary.md](references/crd-summary.md) for a quick overview of all fields.

## Key CRDs

Full schemas are in `openshift/crds/nfd/`. Key CRDs:

| CRD | API Group | Purpose |
|-----|-----------|---------|
| `NodeFeatureDiscovery` | nfd.openshift.io/v1 | Main operator CR — deploys NFD master + workers |
| `NodeFeatureRule` | nfd.openshift.io/v1 | Custom label rules based on detected features |
| `NodeFeature` | nfd.openshift.io/v1 | Per-node feature inventory (auto-created by workers) |
| `NodeFeatureGroup` | nfd.k8s-sigs.io/v1alpha1 | Group nodes by detected features |
| `NodeFeatureRule` | nfd.k8s-sigs.io/v1alpha1 | Upstream K8s-SIG rules (also supported) |
| `NodeFeature` | nfd.k8s-sigs.io/v1alpha1 | Upstream per-node features |

See [references/crd-summary.md](references/crd-summary.md) for field-level details.

## Configuration

### Worker config for GPU-only detection

For clusters that only need NVIDIA GPU detection (used by ocp-gpu-gitops):

```yaml
workerConfig:
  configData: |
    core:
      sleepInterval: 60s
    sources:
      pci:
        deviceClassWhitelist:
          - "03"      # Display controller (covers all GPUs)
          - "12"      # Processing accelerators (compute GPUs like H100)
        deviceLabelFields:
          - "vendor"
```

This produces labels like:
```
feature.node.kubernetes.io/pci-10de.present=true    # NVIDIA vendor ID
feature.node.kubernetes.io/pci-10de.sriov.capable=true  # SR-IOV if supported
```

### Custom NodeFeatureRule — label GPU model

```yaml
apiVersion: nfd.openshift.io/v1
kind: NodeFeatureRule
metadata:
  name: nvidia-gpu-model
  namespace: openshift-nfd
spec:
  rules:
    - name: "nvidia-h100"
      labels:
        nvidia.com/gpu.model: "H100"
      matchFeatures:
        - feature: pci.device
          matchExpressions:
            vendor: {op: In, value: ["10de"]}
            device: {op: In, value: ["2330", "2331"]}   # H100 PCI device IDs
    - name: "nvidia-a100"
      labels:
        nvidia.com/gpu.model: "A100"
      matchFeatures:
        - feature: pci.device
          matchExpressions:
            vendor: {op: In, value: ["10de"]}
            device: {op: In, value: ["20b0", "20b2", "20f1"]}  # A100 variants
```

## Project-Specific Configuration (outpatient-flow-analytics)

### Labels used by this project

The project relies on these NFD/GPU-operator-generated labels for scheduling:

| Label | Set by | Used for |
|-------|--------|----------|
| `nvidia.com/gpu.present=true` | GPU Operator (via NFD detection) | GPU task nodeSelector |
| `feature.node.kubernetes.io/pci-10de.present=true` | NFD | GPU node detection |

### Scheduling rules

**Non-GPU workloads** (PostgreSQL, ETL, generator, viewer) use anti-affinity:
```yaml
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
        - matchExpressions:
            - key: nvidia.com/gpu.present
              operator: DoesNotExist
```

**GPU workloads** (analytics job, Tekton GPU task) use nodeSelector:
```yaml
nodeSelector:
  nvidia.com/gpu.present: "true"
tolerations:
  - key: nvidia.com/gpu
    operator: Exists
    effect: NoSchedule
```

## Fallback: Direct Installation

> Use this procedure only on clusters **without GitOps**. For GitOps clusters,
> NFD is managed by the ocp-gpu-gitops ArgoCD app (see
> [How NFD is installed](#how-nfd-is-installed)).

The bundled `install.sh` automates every step below and is idempotent:

```bash
bash .github/skills/nfd/scripts/install.sh
```

<details>
<summary>Manual steps (expand if you need to apply selectively)</summary>

### Step 1 — Create Namespace and OperatorGroup

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: openshift-nfd
  labels:
    openshift.io/cluster-monitoring: "true"
  annotations:
    openshift.io/display-name: "Node Feature Discovery Operator"
---
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: nfd-group
  namespace: openshift-nfd
spec:
  targetNamespaces:
    - openshift-nfd
```

### Step 2 — Create Subscription

```yaml
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: nfd
  namespace: openshift-nfd
spec:
  channel: stable
  installPlanApproval: Automatic
  name: nfd
  source: redhat-operators
  sourceNamespace: openshift-marketplace
```

### Step 3 — Wait for operator

```bash
oc get csv -n openshift-nfd -w
# Wait until phase = Succeeded
```

### Step 4 — Create NodeFeatureDiscovery instance

```yaml
apiVersion: nfd.openshift.io/v1
kind: NodeFeatureDiscovery
metadata:
  name: nfd-instance
  namespace: openshift-nfd
spec:
  operand:
    image: registry.redhat.io/openshift4/ose-node-feature-discovery-rhel9:v4.20
    imagePullPolicy: IfNotPresent
    servicePort: 12000
  topologyUpdater: false
  workerConfig:
    configData: |
      core:
        sleepInterval: 60s
      sources:
        pci:
          deviceClassWhitelist:
            - "0200"    # Ethernet controller
            - "03"      # Display controller (GPUs)
            - "12"      # Processing accelerators
          deviceLabelFields:
            - "vendor"
```

### Step 5 — Create RBAC for NFD components

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: nfd-master-nodefeature-reader
rules:
  - apiGroups: ["nfd.k8s-sigs.io"]
    resources: ["nodefeatures"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: nfd-master-nodefeaturerules-reader
rules:
  - apiGroups: ["nfd.k8s-sigs.io"]
    resources: ["nodefeaturerules"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: nfd-nodefeature-writer
rules:
  - apiGroups: ["nfd.k8s-sigs.io"]
    resources: ["nodefeatures"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: nfd-master-nodefeature-access
subjects:
  - kind: ServiceAccount
    name: nfd-master
    namespace: openshift-nfd
roleRef:
  kind: ClusterRole
  name: nfd-master-nodefeature-reader
  apiGroup: rbac.authorization.k8s.io
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: nfd-master-nodefeaturerules-access
subjects:
  - kind: ServiceAccount
    name: nfd-master
    namespace: openshift-nfd
roleRef:
  kind: ClusterRole
  name: nfd-master-nodefeaturerules-reader
  apiGroup: rbac.authorization.k8s.io
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: nfd-worker-nodefeature-write-access
subjects:
  - kind: ServiceAccount
    name: nfd-worker
    namespace: openshift-nfd
roleRef:
  kind: ClusterRole
  name: nfd-nodefeature-writer
  apiGroup: rbac.authorization.k8s.io
```

### Step 6 — Verify

```bash
bash .github/skills/nfd/scripts/verify.sh
```

</details>

## Uninstallation

```bash
# Delete NFD instance first
oc delete nodefeaturediscovery nfd-instance -n openshift-nfd

# Delete RBAC
oc delete clusterrolebinding nfd-master-nodefeature-access nfd-master-nodefeaturerules-access nfd-worker-nodefeature-write-access
oc delete clusterrole nfd-master-nodefeature-reader nfd-master-nodefeaturerules-reader nfd-nodefeature-writer

# Delete Subscription
oc delete sub nfd -n openshift-nfd
oc delete csv -n openshift-nfd $(oc get csv -n openshift-nfd -o name)

# Delete namespace
oc delete namespace openshift-nfd
```
