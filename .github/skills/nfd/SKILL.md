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
- Installing or upgrading the NFD operator
- Configuring hardware detection for GPU, FPGA, or other PCI devices
- Setting up node labels for workload scheduling (especially GPU workloads)
- Creating custom NodeFeatureRules for advanced label logic
- Troubleshooting missing node labels or NFD worker/master pod issues
- Preparing nodes for the NVIDIA GPU Operator (NFD is a prerequisite)

## Installation

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

### GitOps installation

If using the ocp-gpu-gitops pattern, NFD is installed automatically at sync wave 2:

```bash
oc apply -f https://raw.githubusercontent.com/samueltauil/ocp-gpu-gitops/main/gitops/manifests/cluster/bootstrap/base/bigbang-app.yaml
```

## Troubleshooting

### No labels appearing on GPU nodes

```bash
# Check NFD worker pods are running on GPU nodes
oc get pods -n openshift-nfd -l app=nfd-worker -o wide

# Check NFD master is running
oc get pods -n openshift-nfd -l app=nfd-master

# View detected features for a specific node
oc get nodefeature -n openshift-nfd
oc get nodefeature <node-name> -n openshift-nfd -o yaml | grep -A20 "pci"

# Verify PCI device class whitelist includes GPU classes
oc get nodefeaturediscovery nfd-instance -n openshift-nfd -o yaml | grep -A10 "deviceClassWhitelist"
```

### NFD worker CrashLoopBackOff

```bash
# Check logs
oc logs -n openshift-nfd -l app=nfd-worker --tail=30

# Common causes:
# - Invalid workerConfig YAML → check syntax
# - RBAC issues → verify ClusterRoleBindings exist
# - Image pull error → check image reference and pull secret
```

### Labels present but GPU operator not using them

The GPU operator looks for `feature.node.kubernetes.io/pci-10de.present=true` (NVIDIA vendor ID). Verify:

```bash
oc get nodes -l feature.node.kubernetes.io/pci-10de.present=true -o name
```

If empty but you know GPUs are present:
- Ensure PCI class `03` and `12` are in the whitelist
- Ensure `vendor` is in `deviceLabelFields`
- Restart NFD workers: `oc delete pods -n openshift-nfd -l app=nfd-worker`

### NodeFeatureDiscovery CR not reconciling

```bash
# Check operator logs
oc logs -n openshift-nfd deploy/nfd-controller-manager --tail=50

# Check CR status
oc get nodefeaturediscovery nfd-instance -n openshift-nfd -o yaml | grep -A10 "status:"
```

## Verification checklist

```bash
echo "=== Subscription ==="
oc get sub nfd -n openshift-nfd -o jsonpath='{.status.currentCSV}'

echo "=== CSV Phase ==="
oc get csv -n openshift-nfd -o jsonpath='{.items[0].status.phase}'

echo "=== NFD Instance ==="
oc get nodefeaturediscovery -n openshift-nfd --no-headers

echo "=== Master Pod ==="
oc get pods -n openshift-nfd -l app=nfd-master --no-headers

echo "=== Worker Pods ==="
oc get pods -n openshift-nfd -l app=nfd-worker --no-headers

echo "=== GPU Nodes (PCI 10de) ==="
oc get nodes -l feature.node.kubernetes.io/pci-10de.present=true -o name

echo "=== Sample Node Labels ==="
GPU_NODE=$(oc get nodes -l feature.node.kubernetes.io/pci-10de.present=true -o name | head -1)
if [ -n "$GPU_NODE" ]; then
  oc get "$GPU_NODE" -o json | python3 -c "
import json,sys
labels = json.load(sys.stdin)['metadata']['labels']
for k,v in sorted(labels.items()):
    if 'feature.node' in k or 'nvidia' in k:
        print(f'  {k}={v}')
"
fi
```

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
