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

# ArgoCD configuration checks
echo ""
echo "--- Configuration ---"

KUSTOMIZE_OPTS=$(oc get argocd openshift-gitops -n openshift-gitops \
  -o jsonpath='{.spec.kustomizeBuildOptions}' 2>/dev/null || echo "")
if echo "$KUSTOMIZE_OPTS" | grep -q "LoadRestrictionsNone"; then
  echo "✓ Kustomize build options: $KUSTOMIZE_OPTS"
  PASS=$((PASS + 1))
else
  echo "✗ Kustomize build options not set — cross-directory refs will fail"
  echo "  Fix: oc patch argocd openshift-gitops -n openshift-gitops --type merge -p '{\"spec\":{\"kustomizeBuildOptions\":\"--load-restrictor LoadRestrictionsNone\"}}'"
  FAIL=$((FAIL + 1))
fi

CTRL_SA="system:serviceaccount:openshift-gitops:openshift-gitops-argocd-application-controller"
HAS_ADMIN=$(oc get clusterrolebindings -o json 2>/dev/null | \
  python3 -c "
import json,sys
data=json.load(sys.stdin)
for i in data['items']:
  if i.get('roleRef',{}).get('name')!='cluster-admin': continue
  for s in i.get('subjects',[]):
    if s.get('kind')=='ServiceAccount' and s.get('name')=='openshift-gitops-argocd-application-controller' and s.get('namespace')=='openshift-gitops':
      print('yes'); sys.exit(0)
print('no')" 2>/dev/null || echo "no")
if [ "$HAS_ADMIN" = "yes" ]; then
  echo "✓ App controller has cluster-admin"
  PASS=$((PASS + 1))
else
  echo "✗ App controller missing cluster-admin — CRD sync will fail"
  echo "  Fix: oc create clusterrolebinding openshift-gitops-argocd-controller-cluster-admin --clusterrole=cluster-admin --serviceaccount=openshift-gitops:openshift-gitops-argocd-application-controller"
  FAIL=$((FAIL + 1))
fi

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
