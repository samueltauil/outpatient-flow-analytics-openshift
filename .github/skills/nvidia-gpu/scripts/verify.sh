#!/usr/bin/env bash
# Verify NVIDIA GPU Operator health
# Exit 0 = healthy, non-zero = problem found
set -euo pipefail

PASS=0
FAIL=0
check() {
  local name="$1" cmd="$2"
  result=$(eval "$cmd" 2>/dev/null) || result="NOT FOUND"
  if echo "$result" | grep -qiE 'not found|error|false|failed|^$'; then
    echo "✗ $name: $result"
    FAIL=$((FAIL + 1))
  else
    echo "✓ $name: $result"
    PASS=$((PASS + 1))
  fi
}

echo "=== NVIDIA GPU Operator Health Check ==="
echo ""

check "Subscription" \
  "oc get sub gpu-operator-certified -n nvidia-gpu-operator -o jsonpath='{.status.currentCSV}'"

check "CSV Phase" \
  "oc get csv -n nvidia-gpu-operator -o jsonpath='{.items[0].status.phase}'"

check "ClusterPolicy State" \
  "oc get clusterpolicy gpu-cluster-policy -o jsonpath='{.status.state}'"

# Component pods
echo ""
echo "--- Component Pods ---"

for COMPONENT in nvidia-device-plugin-daemonset nvidia-dcgm-exporter nvidia-operator-validator; do
  COUNT=$(oc get pods -n nvidia-gpu-operator -l app="$COMPONENT" --no-headers 2>/dev/null | grep -c Running) || COUNT=0
  if [ "$COUNT" -gt 0 ]; then
    echo "✓ $COMPONENT: $COUNT running"
    PASS=$((PASS + 1))
  else
    TOTAL=$(oc get pods -n nvidia-gpu-operator -l app="$COMPONENT" --no-headers 2>/dev/null | wc -l) || TOTAL=0
    if [ "$TOTAL" -gt 0 ]; then
      echo "✗ $COMPONENT: 0 running ($TOTAL total)"
      FAIL=$((FAIL + 1))
    else
      echo "· $COMPONENT: not deployed (may be expected if no GPU nodes)"
    fi
  fi
done

# Driver daemonset uses a different label
DRIVER_COUNT=$(oc get pods -n nvidia-gpu-operator -l openshift.driver-toolkit=true --no-headers 2>/dev/null | grep -c Running) || DRIVER_COUNT=0
if [ "$DRIVER_COUNT" -gt 0 ]; then
  echo "✓ nvidia-driver-daemonset: $DRIVER_COUNT running"
  PASS=$((PASS + 1))
else
  DRIVER_TOTAL=$(oc get pods -n nvidia-gpu-operator -l openshift.driver-toolkit=true --no-headers 2>/dev/null | wc -l) || DRIVER_TOTAL=0
  if [ "$DRIVER_TOTAL" -gt 0 ]; then
    echo "✗ nvidia-driver-daemonset: 0 running ($DRIVER_TOTAL total)"
    FAIL=$((FAIL + 1))
  else
    echo "· nvidia-driver-daemonset: not deployed (may be expected if no GPU nodes)"
  fi
fi

# GPU nodes
echo ""
echo "--- GPU Resources ---"
GPU_NODES=$(oc get nodes -l nvidia.com/gpu.present=true --no-headers 2>/dev/null | wc -l)
if [ "$GPU_NODES" -gt 0 ]; then
  echo "✓ GPU nodes: $GPU_NODES"
  oc get nodes -l nvidia.com/gpu.present=true \
    -o custom-columns='NAME:.metadata.name,GPUs:.status.allocatable.nvidia\.com/gpu' \
    --no-headers 2>/dev/null | while read line; do
    echo "  → $line"
  done
  PASS=$((PASS + 1))
else
  echo "· No GPU nodes detected"
fi

# nvidia-smi test
echo ""
echo "--- nvidia-smi ---"
DRIVER_POD=$(oc get pods -n nvidia-gpu-operator -l openshift.driver-toolkit=true -o name 2>/dev/null | head -1)
if [ -n "$DRIVER_POD" ]; then
  SMI_OUT=$(oc exec -n nvidia-gpu-operator "$DRIVER_POD" -- nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>/dev/null) || SMI_OUT=""
  if [ -n "$SMI_OUT" ]; then
    echo "✓ nvidia-smi: $SMI_OUT"
    PASS=$((PASS + 1))
  else
    echo "✗ nvidia-smi failed"
    FAIL=$((FAIL + 1))
  fi
else
  echo "· No driver toolkit pod found"
fi

# DCGM metrics
echo ""
echo "--- DCGM Metrics ---"
DCGM_POD=$(oc get pods -n nvidia-gpu-operator -l app=nvidia-dcgm-exporter -o name 2>/dev/null | head -1)
if [ -n "$DCGM_POD" ]; then
  METRIC_COUNT=$(oc exec -n nvidia-gpu-operator "$DCGM_POD" -- curl -s localhost:9400/metrics 2>/dev/null | grep -c "^DCGM" || echo "0")
  if [ "$METRIC_COUNT" -gt 0 ]; then
    echo "✓ DCGM exporting $METRIC_COUNT metric families"
    PASS=$((PASS + 1))
  else
    echo "✗ DCGM exporter not producing metrics"
    FAIL=$((FAIL + 1))
  fi
else
  echo "· No DCGM exporter pod found"
fi

# Project-specific SCC check (RBAC-based or legacy SCC users field)
echo ""
echo "--- Project SCC (optional) ---"
if oc get namespace central-analytics &>/dev/null; then
  SCC_USERS=$(oc get scc nonroot-v2 -o jsonpath='{.users}' 2>/dev/null || echo "")
  for SA in gpu-analytics-sa pipeline-sa; do
    if echo "$SCC_USERS" | grep -q "$SA"; then
      echo "✓ $SA has nonroot-v2 SCC (direct)"
    elif oc get rolebinding -n central-analytics -o json 2>/dev/null | \
         python3 -c "
import json,sys
data=json.load(sys.stdin)
sa='$SA'
for rb in data.get('items',[]):
  role=rb.get('roleRef',{}).get('name','')
  if 'nonroot' not in role: continue
  for s in rb.get('subjects',[]):
    if s.get('name')==sa:
      print('yes'); sys.exit(0)
print('no')" 2>/dev/null | grep -q "yes"; then
      echo "✓ $SA has nonroot-v2 SCC (via RBAC)"
    else
      echo "⚠ $SA missing nonroot-v2 — run: oc adm policy add-scc-to-user nonroot-v2 -z $SA -n central-analytics"
    fi
  done
else
  echo "· central-analytics namespace not found (project not deployed yet)"
fi

echo ""
echo "=== Result: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
