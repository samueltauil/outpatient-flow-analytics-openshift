#!/usr/bin/env bash
# Install NVIDIA GPU Operator via OLM
# Idempotent — safe to re-run.
# PREREQUISITE: NFD operator must be installed first.
set -euo pipefail

echo "=== NVIDIA GPU Operator Install ==="

CHANNEL="${1:-v25.3}"

# Pre-check: NFD must be running
if ! oc get nodefeaturediscovery -n openshift-nfd &>/dev/null; then
  echo "✗ NFD operator not found. Install NFD first:"
  echo "  bash .github/skills/nfd/scripts/install.sh"
  exit 1
fi
echo "✓ NFD operator detected"

GPU_NODES=$(oc get nodes -l feature.node.kubernetes.io/pci-10de.present=true --no-headers 2>/dev/null | wc -l)
echo "· GPU nodes detected by NFD: $GPU_NODES"
[ "$GPU_NODES" -eq 0 ] && echo "⚠ Warning: No NVIDIA GPU nodes found — operator will install but driver pods won't schedule"

# Step 1: Namespace
if oc get namespace nvidia-gpu-operator &>/dev/null; then
  echo "✓ Namespace nvidia-gpu-operator exists"
else
  echo "→ Creating namespace..."
  oc apply -f - <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: nvidia-gpu-operator
  labels:
    openshift.io/cluster-monitoring: "true"
  annotations:
    openshift.io/display-name: "NVIDIA GPU Operator"
EOF
fi

# Step 2: OperatorGroup
if oc get operatorgroup nvidia-gpu-operator-group -n nvidia-gpu-operator &>/dev/null; then
  echo "✓ OperatorGroup exists"
else
  echo "→ Creating OperatorGroup..."
  oc apply -f - <<EOF
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: nvidia-gpu-operator-group
  namespace: nvidia-gpu-operator
spec:
  targetNamespaces:
    - nvidia-gpu-operator
EOF
fi

# Step 3: Subscription
if oc get subscription gpu-operator-certified -n nvidia-gpu-operator &>/dev/null; then
  CURRENT=$(oc get subscription gpu-operator-certified -n nvidia-gpu-operator \
    -o jsonpath='{.status.currentCSV}' 2>/dev/null || echo "pending")
  echo "✓ Subscription already exists (CSV: $CURRENT)"
else
  echo "→ Creating Subscription (channel: $CHANNEL)..."
  oc apply -f - <<EOF
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: gpu-operator-certified
  namespace: nvidia-gpu-operator
spec:
  channel: ${CHANNEL}
  installPlanApproval: Automatic
  name: gpu-operator-certified
  source: certified-operators
  sourceNamespace: openshift-marketplace
EOF
  echo "✓ Subscription created"
fi

# Wait for CSV
echo "→ Waiting for CSV to reach Succeeded phase..."
for i in $(seq 1 90); do
  PHASE=$(oc get csv -n nvidia-gpu-operator -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "Waiting")
  if [ "$PHASE" = "Succeeded" ]; then
    CSV=$(oc get csv -n nvidia-gpu-operator -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    echo "✓ CSV ready: $CSV"
    break
  fi
  [ "$i" -eq 90 ] && { echo "✗ Timeout waiting for CSV (last phase: $PHASE)"; exit 1; }
  sleep 5
done

# Step 4: ClusterPolicy
if oc get clusterpolicy gpu-cluster-policy &>/dev/null; then
  echo "✓ ClusterPolicy already exists"
else
  echo "→ Creating ClusterPolicy..."
  oc apply -f - <<'EOF'
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
EOF
  echo "✓ ClusterPolicy created"
fi

# Wait for ClusterPolicy to be ready (only if GPU nodes exist)
if [ "$GPU_NODES" -gt 0 ]; then
  echo "→ Waiting for GPU stack to initialize (this takes several minutes)..."
  for i in $(seq 1 120); do
    STATE=$(oc get clusterpolicy gpu-cluster-policy -o jsonpath='{.status.state}' 2>/dev/null || echo "waiting")
    if [ "$STATE" = "ready" ]; then
      echo "✓ ClusterPolicy state: ready"
      break
    fi
    [ "$i" -eq 120 ] && { echo "⚠ ClusterPolicy not ready yet (state: $STATE) — GPU driver build may still be running"; break; }
    sleep 10
  done
else
  echo "· Skipping GPU stack wait (no GPU nodes detected)"
fi

# Grant SCC for project RAPIDS workloads
echo ""
echo "→ Granting nonroot-v2 SCC for RAPIDS workloads..."
if oc get namespace central-analytics &>/dev/null; then
  oc adm policy add-scc-to-user nonroot-v2 -z gpu-analytics-sa -n central-analytics 2>/dev/null && \
    echo "✓ nonroot-v2 granted to gpu-analytics-sa" || echo "· gpu-analytics-sa not found yet"
  oc adm policy add-scc-to-user nonroot-v2 -z pipeline-sa -n central-analytics 2>/dev/null && \
    echo "✓ nonroot-v2 granted to pipeline-sa" || echo "· pipeline-sa not found yet"
else
  echo "· central-analytics namespace not found (will grant SCC when project is deployed)"
fi

echo ""
echo "=== Installation Complete ==="
echo "Run verify.sh to check GPU health."
echo "Validate GPUs: oc exec -n nvidia-gpu-operator <driver-pod> -- nvidia-smi"
