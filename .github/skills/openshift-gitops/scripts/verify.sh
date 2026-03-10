#!/usr/bin/env bash
# Verify OpenShift GitOps (ArgoCD) operator health
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

echo "=== OpenShift GitOps Health Check ==="
echo ""

check "Subscription" \
  "oc get sub openshift-gitops-operator -n openshift-operators -o jsonpath='{.status.currentCSV}'"

check "CSV Phase" \
  "oc get csv -n openshift-gitops -o jsonpath='{.items[0].status.phase}'"

check "ArgoCD Instance" \
  "oc get argocd -n openshift-gitops -o jsonpath='{.items[0].metadata.name}'"

check "Server Deployment" \
  "oc get deployment openshift-gitops-server -n openshift-gitops -o jsonpath='{.status.availableReplicas}' | xargs printf '%s replicas available'"

check "Server Route" \
  "oc get route openshift-gitops-server -n openshift-gitops -o jsonpath='{.spec.host}'"

check "Application Controller" \
  "oc get pods -n openshift-gitops -l app.kubernetes.io/name=openshift-gitops-application-controller -o jsonpath='{.items[0].status.phase}'"

check "Repo Server" \
  "oc get pods -n openshift-gitops -l app.kubernetes.io/name=openshift-gitops-repo-server -o jsonpath='{.items[0].status.phase}'"

# Check for any Applications
echo ""
echo "--- Applications ---"
APP_COUNT=$(oc get applications -n openshift-gitops --no-headers 2>/dev/null | wc -l)
if [ "$APP_COUNT" -gt 0 ]; then
  oc get applications -n openshift-gitops \
    -o custom-columns='NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status' \
    --no-headers 2>/dev/null
else
  echo "· No Applications deployed yet"
fi

echo ""
echo "=== Result: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
