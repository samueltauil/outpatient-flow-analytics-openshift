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

# NVIDIA GPU Operator — Troubleshooting & Configuration

## When to use this skill

Use this skill when:
- **Troubleshooting** driver pods not starting, nvidia-smi failures, or GPU not detected
- **Diagnosing** ClusterPolicy not reaching "ready" state
- **Fixing** SCC issues for RAPIDS/cuML containers (nonroot-v2, UID 1001)
- **Debugging** DCGM exporter metrics or ServiceMonitor scraping problems
- **Resolving** GPU scheduling issues (pods pending, `nvidia.com/gpu` resource unavailable)
- **Configuring** ClusterPolicy CR (driver, DCGM, device plugin, toolkit, MIG)
- **Setting up** GPU workloads with `nvidia.com/gpu` resource requests
- **Preparing** infrastructure for ML/AI workloads (XGBoost GPU, cuDF, cuML)

## Installation

### Primary: GitOps Installation (ocp-gpu-gitops)

The NVIDIA GPU Operator is installed automatically via the [ocp-gpu-gitops](https://github.com/samueltauil/ocp-gpu-gitops) ArgoCD app-of-apps pattern:

- **Sync-wave 2:** NFD operator is installed first (GPU operator depends on NFD labels)
- **Sync-wave 3:** GPU operator + ClusterPolicy are installed
- **Sync-wave 4:** DCGM Grafana dashboard is deployed

To bootstrap everything at once:

```bash
oc apply -f https://raw.githubusercontent.com/samueltauil/ocp-gpu-gitops/main/gitops/manifests/cluster/bootstrap/base/bigbang-app.yaml
```

ArgoCD will reconcile NFD → GPU Operator → DCGM Dashboard in the correct order. No manual steps are required after applying the bigbang app.

### Fallback: Direct Installation (install.sh)

For non-GitOps clusters or when ArgoCD is not available, use the bundled install script:

```bash
bash .github/skills/nvidia-gpu/scripts/install.sh
```

The script is idempotent and performs these steps:

1. Creates the `nvidia-gpu-operator` namespace with cluster-monitoring label
2. Creates the OperatorGroup
3. Creates the Subscription (from `certified-operators`, channel `v25.3`)
4. Waits for CSV to reach `Succeeded` phase
5. Creates the ClusterPolicy CR
6. Waits for the validator pod to become Ready

## Prerequisites

**NFD operator must be installed and running first.** The GPU operator depends on NFD labels to discover GPU-capable nodes. Specifically, it looks for:

```
feature.node.kubernetes.io/pci-10de.present=true
```

Verify: `oc get nodes -l feature.node.kubernetes.io/pci-10de.present=true`

## Diagnostics: Start Here

**Always run `verify.sh` as the first step for any GPU issue:**

```bash
bash .github/skills/nvidia-gpu/scripts/verify.sh
```

The script returns exit code 0 if the GPU stack is healthy, or non-zero with diagnostics pointing to the problem. It checks:

- Subscription and CSV status
- ClusterPolicy state
- Driver pods on GPU nodes
- Device plugin pods
- DCGM exporter pods
- Validator pods
- GPU node allocatable resources
- nvidia-smi output

If `verify.sh` reports a specific failing component, jump to the matching troubleshooting section below.

## Troubleshooting

### Driver pods not starting or failing on GPU nodes

```bash
# Check driver pod status
oc get pods -n nvidia-gpu-operator -l app=nvidia-driver-daemonset

# Check logs for errors
oc logs -n nvidia-gpu-operator -l app=nvidia-driver-daemonset --tail=50

# Describe the pod for events
oc describe pod -n nvidia-gpu-operator -l app=nvidia-driver-daemonset | tail -30
```

**Common causes:**
- **Secure Boot enabled** → Disable in BIOS, or use a pre-built driver image
- **Kernel version mismatch** → The driver build fails if the Driver Toolkit image doesn't match the node kernel. Check: `oc debug node/<gpu-node> -- chroot /host uname -r`
- **Missing RHEL entitlement** → Driver compilation requires RHEL entitlement on the node. Check: `oc debug node/<gpu-node> -- chroot /host ls /etc/pki/entitlement/`
- **Node not labeled by NFD** → Driver daemonset only targets nodes with `feature.node.kubernetes.io/pci-10de.present=true`

### nvidia-smi not working / GPU not detected

```bash
# Test nvidia-smi via driver pod
oc -n nvidia-gpu-operator get pods -l openshift.driver-toolkit=true -o name | while read pod; do
  echo "=== $pod ==="
  oc exec -n nvidia-gpu-operator -it "$pod" -- nvidia-smi
done
```

**If "No devices were found":**
1. Check NFD labels exist: `oc get nodes -l feature.node.kubernetes.io/pci-10de.present=true`
2. Check PCI hardware: `oc debug node/<gpu-node> -- chroot /host lspci | grep -i nvidia`
3. Check driver module is loaded: `oc debug node/<gpu-node> -- chroot /host lsmod | grep nvidia`
4. If the driver module is missing, check the driver pod logs for compilation errors

### ClusterPolicy not reaching "ready" state

```bash
# Check ClusterPolicy status
oc get clusterpolicy gpu-cluster-policy -o jsonpath='{.status.state}{"\n"}'

# Detailed status of each component
oc get clusterpolicy gpu-cluster-policy -o yaml | grep -A30 "status:"

# Check operator logs
oc logs -n nvidia-gpu-operator deploy/gpu-operator --tail=100
```

**Common causes:**
- **NFD not running** → ClusterPolicy waits for NFD labels. Install NFD first (sync-wave 2 in GitOps)
- **No GPU nodes** → Verify GPU nodes exist: `oc get nodes -l feature.node.kubernetes.io/pci-10de.present=true`
- **Driver pods failing** → See "Driver pods not starting" above
- **Validator failing** → Check validator pod: `oc logs -n nvidia-gpu-operator -l app=nvidia-operator-validator --tail=50`

### SCC issues: RAPIDS containers need nonroot-v2 (UID 1001)

RAPIDS images (cuDF, cuML, XGBoost GPU) run as UID 1001 (rapids user). OpenShift's default `restricted-v2` SCC only allows random high UIDs, which causes permission errors.

**Symptoms:** Pod fails with `CrashLoopBackOff` or logs show permission denied errors.

```bash
# Check which SCC the pod received
oc get pod <pod-name> -n central-analytics -o jsonpath='{.metadata.annotations.openshift\.io/scc}{"\n"}'

# If "restricted" or "restricted-v2", grant nonroot-v2:
oc adm policy add-scc-to-user nonroot-v2 -z gpu-analytics-sa -n central-analytics
oc adm policy add-scc-to-user nonroot-v2 -z pipeline-sa -n central-analytics
```

**Pod security context must match:**
```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1001
  runAsGroup: 1001
  fsGroup: 1001
```

### DCGM exporter not producing metrics / ServiceMonitor not scraping

```bash
# Check DCGM pods are running
oc get pods -n nvidia-gpu-operator -l app=nvidia-dcgm-exporter

# Test metrics endpoint directly
DCGM_POD=$(oc get pods -n nvidia-gpu-operator -l app=nvidia-dcgm-exporter -o name | head -1)
oc exec -n nvidia-gpu-operator "$DCGM_POD" -- curl -s localhost:9400/metrics | head -20

# Check ServiceMonitor exists
oc get servicemonitor -n nvidia-gpu-operator

# Verify Prometheus is scraping
oc -n openshift-monitoring exec -c prometheus prometheus-k8s-0 -- \
  curl -s 'http://localhost:9090/api/v1/targets' | python3 -c "
import json,sys
targets = json.load(sys.stdin)
for t in targets.get('data',{}).get('activeTargets',[]):
    if 'dcgm' in t.get('labels',{}).get('job',''):
        print(f\"Job: {t['labels']['job']}  State: {t['health']}  Endpoint: {t['scrapeUrl']}\")
"
```

**If ServiceMonitor is missing:** Check that `dcgmExporter.serviceMonitor.enabled: true` is set in ClusterPolicy. The DCGM dashboard (sync-wave 4 in GitOps) also depends on these metrics.

### GPU scheduling: pods pending, nvidia.com/gpu not available

```bash
# Check allocatable GPU resources on nodes
oc get nodes -l nvidia.com/gpu.present=true \
  -o jsonpath='{range .items[*]}{.metadata.name}: allocatable={.status.allocatable.nvidia\.com/gpu}, capacity={.status.capacity.nvidia\.com/gpu}{"\n"}{end}'

# Check device plugin pod is running
oc get pods -n nvidia-gpu-operator -l app=nvidia-device-plugin-daemonset

# Find pods currently using GPUs
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

**Common causes:**
- **Device plugin not running** → Restart it or check ClusterPolicy
- **All GPUs allocated** → Another pod holds the GPU. Check with the script above
- **Node tainted** → Ensure the pod has the correct toleration: `nvidia.com/gpu: Exists: NoSchedule`
- **Missing nodeSelector** → Pod needs `nvidia.com/gpu.present: "true"` nodeSelector

### XGBoost 2.x GPU configuration

XGBoost 2.x deprecated `tree_method='gpu_hist'`. Code using the old parameter will fall back to CPU silently.

**Fix:** Replace in your training code:
```python
# Old (deprecated — silently uses CPU in XGBoost 2.x)
model = xgb.XGBClassifier(tree_method='gpu_hist')

# New (correct for XGBoost 2.x+)
model = xgb.XGBClassifier(tree_method='hist', device='cuda')
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

RAPIDS images run as UID 1001 (rapids user in conda group). Standard restricted SCC blocks this. See [SCC troubleshooting](#scc-issues-rapids-containers-need-nonroot-v2-uid-1001) for diagnosis and fix.

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

**XGBoost GPU configuration:**
- XGBoost 2.x+ deprecated `tree_method='gpu_hist'`. See [XGBoost troubleshooting](#xgboost-2x-gpu-configuration) for the correct replacement.

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
