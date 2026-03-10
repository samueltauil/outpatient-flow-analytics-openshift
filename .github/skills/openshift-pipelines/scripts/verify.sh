#!/usr/bin/env bash
# Verify OpenShift Pipelines operator health
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

echo "=== OpenShift Pipelines Health Check ==="
echo ""

check "Subscription" \
  "oc get sub openshift-pipelines-operator-rh -n openshift-operators -o jsonpath='{.status.currentCSV}'"

check "CSV Phase" \
  "oc get csv -n openshift-pipelines -o jsonpath='{.items[0].status.phase}'"

check "TektonConfig Ready" \
  "oc get tektonconfig config -o jsonpath='{.status.conditions[?(@.type==\"Ready\")].status}'"

check "Tekton Version" \
  "oc get tektonconfig config -o jsonpath='{.status.version}'"

check "Pipeline Controller" \
  "oc get pods -n openshift-pipelines -l app=tekton-pipelines-controller -o jsonpath='{.items[0].status.phase}'"

check "Trigger Controller" \
  "oc get pods -n openshift-pipelines -l app=tekton-triggers-controller -o jsonpath='{.items[0].status.phase}'"

check "Pipeline CRD" \
  "oc get crd pipelines.tekton.dev -o jsonpath='{.metadata.name}'"

# Project-specific checks
echo ""
echo "--- Project-specific (optional) ---"

if oc get namespace central-analytics &>/dev/null; then
  check "pipeline-sa SCC" \
    "oc get scc nonroot-v2 -o jsonpath='{.users}' | grep -o 'pipeline-sa' || echo 'NOT GRANTED — run: oc adm policy add-scc-to-user nonroot-v2 -z pipeline-sa -n central-analytics'"

  check "Tasks in central-analytics" \
    "oc get tasks -n central-analytics --no-headers | wc -l | xargs printf '%s tasks found'"

  check "Pipeline in central-analytics" \
    "oc get pipelines -n central-analytics --no-headers | wc -l | xargs printf '%s pipelines found'"
else
  echo "· central-analytics namespace not found (project not deployed yet)"
fi

echo ""
echo "=== Result: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
