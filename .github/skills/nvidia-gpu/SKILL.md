---
name: nvidia-gpu
description: >
  Install, configure, fix, and troubleshoot the NVIDIA GPU Operator on OpenShift.
  Use when working with GPU workloads, ClusterPolicy CR, NVIDIADriver CR, DCGM monitoring,
  device plugin, container toolkit, MIG, or the gpu-operator-certified subscription. Covers
  OLM installation from certified-operators, ClusterPolicy configuration, nonroot-v2 SCC
  for RAPIDS/cuML workloads (UID 1001), DCGM ServiceMonitor, and GPU scheduling for the
  outpatient-flow-analytics project.
compatibility: Requires OpenShift 4.14+ with cluster-admin access, oc CLI, and GPU-capable nodes. NFD operator must be installed first.
---

# NVIDIA GPU Operator

## When to use this skill

Use this skill when:
- Installing or upgrading the NVIDIA GPU Operator
- Configuring the ClusterPolicy CR (driver, DCGM, device plugin, toolkit, MIG)
- Setting up GPU workloads with `nvidia.com/gpu` resource requests
- Configuring SCC for RAPIDS/cuML containers (nonroot-v2, UID 1001)
- Setting up DCGM monitoring (ServiceMonitor, Grafana dashboard)
- Troubleshooting GPU driver pods, device plugin, nvidia-smi, or scheduling issues
- Preparing infrastructure for ML/AI workloads (XGBoost GPU, cuDF, cuML)

## Prerequisites

**NFD operator must be installed and running first.** The GPU operator depends on NFD labels to discover GPU-capable nodes. Specifically, it looks for:

```
feature.node.kubernetes.io/pci-10de.present=true
```

Verify: `oc get nodes -l feature.node.kubernetes.io/pci-10de.present=true`

## Installation

### Step 1 — Create Namespace and OperatorGroup

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: nvidia-gpu-operator
  labels:
    openshift.io/cluster-monitoring: "true"
  annotations:
    openshift.io/display-name: "NVIDIA GPU Operator"
---
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: nvidia-gpu-operator-group
  namespace: nvidia-gpu-operator
spec:
  targetNamespaces:
    - nvidia-gpu-operator
```

### Step 2 — Create Subscription

```yaml
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: gpu-operator-certified
  namespace: nvidia-gpu-operator
spec:
  channel: v25.3
  installPlanApproval: Automatic
  name: gpu-operator-certified
  source: certified-operators
  sourceNamespace: openshift-marketplace
```

**Note:** The GPU operator comes from `certified-operators`, not `redhat-operators`.

### Step 3 — Wait for operator

```bash
oc get csv -n nvidia-gpu-operator -w
# Wait until phase = Succeeded
```

### Step 4 — Create ClusterPolicy

```yaml
apiVersion: nvidia.com/v1
kind: ClusterPolicy
metadata:
  name: gpu-cluster-policy
spec:
  operator:
    defaultRuntime: crio
    initContainer: {}
    runtimeClass: nvidia
  driver:
    enabled: true
    licensingConfig:
      nlsEnabled: false
      configMapName: ""
    certConfig:
      name: ""
    kernelModuleConfig:
      name: ""
    repoConfig:
      configMapName: ""
    virtualTopology:
      config: ""
  dcgm:
    enabled: true
  dcgmExporter:
    serviceMonitor:
      enabled: true
    config:
      name: ""
  devicePlugin: {}
  gfd: {}
  migManager:
    enabled: true
  mig:
    strategy: single
  toolkit:
    enabled: true
  validator:
    plugin:
      env:
        - name: WITH_WORKLOAD
          value: "true"
  nodeStatusExporter:
    enabled: true
  daemonsets: {}
```

### Step 5 — Wait for GPU stack to be ready

```bash
# Watch driver pods come up on GPU nodes
oc get pods -n nvidia-gpu-operator -w

# Wait for the validator to pass
oc wait --for=condition=Ready pod -l app=nvidia-operator-validator \
  -n nvidia-gpu-operator --timeout=600s
```

## Looking up CRD field details

When you need to understand specific configuration fields, enum values, defaults, or nested structures, use the lookup script to query the full OpenAPI schemas in `openshift/crds/gpu-operator-certified/`:

```bash
# List all available CRDs
bash .github/skills/nvidia-gpu/scripts/lookup-crd.sh

# Show top-level spec fields for ClusterPolicy
bash .github/skills/nvidia-gpu/scripts/lookup-crd.sh clusterpolicies

# Drill into nested fields
bash .github/skills/nvidia-gpu/scripts/lookup-crd.sh clusterpolicies spec.driver
bash .github/skills/nvidia-gpu/scripts/lookup-crd.sh clusterpolicies spec.dcgmExporter
bash .github/skills/nvidia-gpu/scripts/lookup-crd.sh clusterpolicies spec.mig
bash .github/skills/nvidia-gpu/scripts/lookup-crd.sh nvidiadrivers spec
```

See [references/crd-summary.md](references/crd-summary.md) for a quick overview of all fields.

## Key CRDs

Full schemas are in `openshift/crds/gpu-operator-certified/`. Key CRDs:

| CRD | Purpose |
|-----|---------|
| `ClusterPolicy` (nvidia.com/v1) | Main CR — configures the entire GPU stack |
| `NVIDIADriver` (nvidia.com/v1alpha1) | Per-node-group driver configuration |

See [references/crd-summary.md](references/crd-summary.md) for field-level details.

## Configuration

### ClusterPolicy key sections

**Driver:**
```yaml
spec:
  driver:
    enabled: true                         # Use in-tree driver or pre-installed
    useNvidiaDriverCRD: false             # Use NVIDIADriver CR per node group
    kernelModuleType: auto                # auto | open | proprietary
    upgradePolicy:
      autoUpgrade: true
      maxParallelUpgrades: 1
      maxUnavailable: "25%"
      drain:
        enable: false
        deleteEmptyDir: false
        force: false
        timeoutSeconds: 300
```

**DCGM Exporter (monitoring):**
```yaml
spec:
  dcgm:
    enabled: true
  dcgmExporter:
    serviceMonitor:
      enabled: true                       # Creates ServiceMonitor for Prometheus
    config:
      name: ""                            # Custom metrics ConfigMap (optional)
```

**Device Plugin:**
```yaml
spec:
  devicePlugin:
    config:
      name: ""                            # Custom device plugin config
      default: ""
    mps:
      root: "/run/nvidia/mps"             # MPS for shared GPU access
```

**MIG (Multi-Instance GPU):**
```yaml
spec:
  mig:
    strategy: single                      # single | mixed
  migManager:
    enabled: true
    config:
      name: ""                            # MIG profile ConfigMap
```

**Sandbox Workloads (vGPU):**
```yaml
spec:
  sandboxWorkloads:
    enabled: false
    defaultWorkload: container            # container | vm-passthrough | vm-vgpu
  vgpuManager:
    enabled: false
  vfioManager:
    enabled: true
```

### DCGM Dashboard (Grafana)

Deploy the DCGM Grafana dashboard as used in ocp-gpu-gitops:

```bash
# From the ocp-gpu-gitops repo
oc apply -f https://raw.githubusercontent.com/samueltauil/ocp-gpu-gitops/main/gitops/manifests/workloads/gpu-dashboard/base/dcgm-dashboard.yaml
```

This creates a ConfigMap in `openshift-config-managed` with the Grafana dashboard JSON. View it at **Observe → Dashboards → NVIDIA DCGM Exporter Dashboard** in the OpenShift console.

## Project-Specific Setup (outpatient-flow-analytics)

### GPU workload configuration

The analytics job uses NVIDIA RAPIDS (cuDF, cuML, XGBoost GPU) on H100 GPUs.

**Container image:** Based on `nvcr.io/nvidia/rapidsai/base:26.02-cuda12-py3.12`

**Critical: SCC for RAPIDS containers**

RAPIDS images run as UID 1001 (rapids user in conda group). Standard restricted SCC blocks this. Grant nonroot-v2:

```bash
oc adm policy add-scc-to-user nonroot-v2 -z gpu-analytics-sa -n central-analytics
oc adm policy add-scc-to-user nonroot-v2 -z pipeline-sa -n central-analytics
```

**GPU Job manifest pattern:**
```yaml
spec:
  template:
    spec:
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
      containers:
        - name: analytics
          image: ghcr.io/samueltauil/hls-analytics-gpu:latest
          resources:
            requests:
              nvidia.com/gpu: "1"
              memory: "4Gi"
              cpu: "2"
            limits:
              nvidia.com/gpu: "1"
              memory: "16Gi"
              cpu: "8"
```

**XGBoost GPU configuration note:**
- XGBoost 2.x+ deprecated `tree_method='gpu_hist'`
- Use `tree_method='hist'` with `device='cuda'` instead

### DCGM ServiceMonitor

The deploy.sh script creates a ServiceMonitor for Prometheus to scrape GPU metrics:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: nvidia-dcgm-exporter
  namespace: nvidia-gpu-operator
spec:
  selector:
    matchLabels:
      app: nvidia-dcgm-exporter
  endpoints:
    - port: gpu-metrics
      interval: 15s
      path: /metrics
```

### GitOps installation

NFD + GPU operator via GitOps (wave 2 → wave 3):

```bash
oc apply -f https://raw.githubusercontent.com/samueltauil/ocp-gpu-gitops/main/gitops/manifests/cluster/bootstrap/base/bigbang-app.yaml
```

## Troubleshooting

### Driver pods not starting

```bash
# Check driver pod status
oc get pods -n nvidia-gpu-operator -l app=nvidia-driver-daemonset

# Check logs
oc logs -n nvidia-gpu-operator -l app=nvidia-driver-daemonset --tail=50

# Common causes:
# - Secure Boot enabled → disable or use pre-built driver
# - Kernel version mismatch → check: oc debug node/<gpu-node> -- chroot /host uname -r
# - Missing entitlement → need RHEL entitlement for driver build
```

### nvidia-smi not working / GPU not detected

```bash
# Test nvidia-smi via driver pod
oc -n nvidia-gpu-operator get pods -l openshift.driver-toolkit=true -o name | while read pod; do
  echo "=== $pod ==="
  oc exec -n nvidia-gpu-operator -it "$pod" -- nvidia-smi
done

# If "No devices found":
# - Check NFD labels: oc get nodes -l feature.node.kubernetes.io/pci-10de.present=true
# - Check PCI: oc debug node/<gpu-node> -- chroot /host lspci | grep -i nvidia
```

### Pod can't schedule — "insufficient nvidia.com/gpu"

```bash
# Check available GPU resources
oc get nodes -l nvidia.com/gpu.present=true -o jsonpath='{range .items[*]}{.metadata.name}: allocatable={.status.allocatable.nvidia\.com/gpu}, allocated={.status.capacity.nvidia\.com/gpu}{"\n"}{end}'

# Check device plugin pod
oc get pods -n nvidia-gpu-operator -l app=nvidia-device-plugin-daemonset

# Check if another pod is using the GPU
oc get pods --all-namespaces -o json | python3 -c "
import json,sys
pods = json.load(sys.stdin)
for p in pods['items']:
    for c in p['spec'].get('containers', []):
        gpu = c.get('resources', {}).get('limits', {}).get('nvidia.com/gpu')
        if gpu:
            print(f\"{p['metadata']['namespace']}/{p['metadata']['name']}: {gpu} GPU(s)\")
"
```

### Permission denied in RAPIDS container (SCC issue)

```bash
# Check which SCC the pod got
oc get pod <pod-name> -n central-analytics -o jsonpath='{.metadata.annotations.openshift\.io/scc}'

# If "restricted" or "restricted-v2", grant nonroot-v2:
oc adm policy add-scc-to-user nonroot-v2 -z <service-account> -n <namespace>

# RAPIDS needs UID 1001 — restricted SCC only allows random high UIDs
```

### ClusterPolicy not reconciling

```bash
# Check ClusterPolicy status
oc get clusterpolicy gpu-cluster-policy -o yaml | grep -A30 "status:"

# Check operator logs
oc logs -n nvidia-gpu-operator deploy/gpu-operator --tail=50

# Common causes:
# - NFD not running → install NFD first
# - No GPU nodes → verify: oc get nodes -l feature.node.kubernetes.io/pci-10de.present=true
```

### DCGM exporter not producing metrics

```bash
# Check DCGM pods
oc get pods -n nvidia-gpu-operator -l app=nvidia-dcgm-exporter

# Test metrics endpoint directly
DCGM_POD=$(oc get pods -n nvidia-gpu-operator -l app=nvidia-dcgm-exporter -o name | head -1)
oc exec -n nvidia-gpu-operator "$DCGM_POD" -- curl -s localhost:9400/metrics | head -20

# Check ServiceMonitor exists
oc get servicemonitor -n nvidia-gpu-operator
```

## Verification checklist

```bash
echo "=== Subscription ==="
oc get sub gpu-operator-certified -n nvidia-gpu-operator -o jsonpath='{.status.currentCSV}'

echo "=== CSV Phase ==="
oc get csv -n nvidia-gpu-operator -o jsonpath='{.items[0].status.phase}'

echo "=== ClusterPolicy ==="
oc get clusterpolicy gpu-cluster-policy -o jsonpath='{.status.state}'

echo "=== Driver Pods ==="
oc get pods -n nvidia-gpu-operator -l app=nvidia-driver-daemonset --no-headers

echo "=== Device Plugin ==="
oc get pods -n nvidia-gpu-operator -l app=nvidia-device-plugin-daemonset --no-headers

echo "=== DCGM Exporter ==="
oc get pods -n nvidia-gpu-operator -l app=nvidia-dcgm-exporter --no-headers

echo "=== Validator ==="
oc get pods -n nvidia-gpu-operator -l app=nvidia-operator-validator --no-headers

echo "=== GPU Nodes ==="
oc get nodes -l nvidia.com/gpu.present=true -o custom-columns='NAME:.metadata.name,GPU_COUNT:.status.allocatable.nvidia\.com/gpu'

echo "=== nvidia-smi ==="
oc -n nvidia-gpu-operator get pods -l openshift.driver-toolkit=true -o name | head -1 | xargs -I{} oc exec -n nvidia-gpu-operator {} -- nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>/dev/null || echo "Cannot run nvidia-smi"
```

## Uninstallation

```bash
# Delete ClusterPolicy first
oc delete clusterpolicy gpu-cluster-policy

# Wait for daemonsets to terminate
oc get pods -n nvidia-gpu-operator -w

# Delete Subscription
oc delete sub gpu-operator-certified -n nvidia-gpu-operator
oc delete csv -n nvidia-gpu-operator $(oc get csv -n nvidia-gpu-operator -o name)

# Delete namespace
oc delete namespace nvidia-gpu-operator

# GPU node labels are cleaned up automatically
```
