#!/usr/bin/env bash
# Verify Node Feature Discovery operator health
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

echo "=== NFD Health Check ==="
echo ""

check "Subscription" \
  "oc get sub nfd -n openshift-nfd -o jsonpath='{.status.currentCSV}'"

check "CSV Phase" \
  "oc get csv -n openshift-nfd -o jsonpath='{.items[0].status.phase}'"

check "NFD Instance" \
  "oc get nodefeaturediscovery nfd-instance -n openshift-nfd -o jsonpath='{.metadata.name}'"

MASTER_COUNT=$(oc get pods -n openshift-nfd -l app=nfd-master --no-headers 2>/dev/null | grep -c Running || echo "0")
if [ "$MASTER_COUNT" -gt 0 ]; then
  echo "✓ NFD Master: $MASTER_COUNT pod(s) running"
  PASS=$((PASS + 1))
else
  echo "✗ NFD Master: no running pods"
  FAIL=$((FAIL + 1))
fi

WORKER_COUNT=$(oc get pods -n openshift-nfd -l app=nfd-worker --no-headers 2>/dev/null | grep -c Running || echo "0")
if [ "$WORKER_COUNT" -gt 0 ]; then
  echo "✓ NFD Workers: $WORKER_COUNT pod(s) running"
  PASS=$((PASS + 1))
else
  echo "✗ NFD Workers: no running pods"
  FAIL=$((FAIL + 1))
fi

# GPU node detection
echo ""
echo "--- GPU Node Detection ---"
GPU_NODES=$(oc get nodes -l feature.node.kubernetes.io/pci-10de.present=true --no-headers 2>/dev/null | wc -l)
if [ "$GPU_NODES" -gt 0 ]; then
  echo "✓ GPU nodes detected: $GPU_NODES"
  oc get nodes -l feature.node.kubernetes.io/pci-10de.present=true \
    -o custom-columns='NAME:.metadata.name' --no-headers 2>/dev/null | while read node; do
    echo "  → $node"
  done
  PASS=$((PASS + 1))
else
  echo "· No GPU nodes detected (this is normal if the cluster has no NVIDIA GPUs)"
fi

echo ""
echo "=== Result: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
