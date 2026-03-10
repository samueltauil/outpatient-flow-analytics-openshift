#!/usr/bin/env bash
# Install OpenShift Pipelines (Tekton) operator via OLM
# Idempotent — safe to re-run.
set -euo pipefail

echo "=== OpenShift Pipelines Operator Install ==="

CHANNEL="${1:-latest}"

# Check if already installed
if oc get subscription openshift-pipelines-operator-rh -n openshift-operators &>/dev/null; then
  CURRENT=$(oc get subscription openshift-pipelines-operator-rh -n openshift-operators \
    -o jsonpath='{.status.currentCSV}' 2>/dev/null || echo "pending")
  echo "✓ Subscription already exists (CSV: $CURRENT)"
else
  echo "→ Creating Subscription (channel: $CHANNEL)..."
  oc apply -f - <<EOF
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: openshift-pipelines-operator-rh
  namespace: openshift-operators
spec:
  channel: ${CHANNEL}
  installPlanApproval: Automatic
  name: openshift-pipelines-operator-rh
  source: redhat-operators
  sourceNamespace: openshift-marketplace
EOF
  echo "✓ Subscription created"
fi

# Wait for CSV to succeed
echo "→ Waiting for CSV to reach Succeeded phase..."
for i in $(seq 1 60); do
  PHASE=$(oc get csv -n openshift-pipelines -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "Waiting")
  if [ "$PHASE" = "Succeeded" ]; then
    CSV=$(oc get csv -n openshift-pipelines -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    echo "✓ CSV ready: $CSV"
    break
  fi
  [ "$i" -eq 60 ] && { echo "✗ Timeout waiting for CSV (last phase: $PHASE)"; exit 1; }
  sleep 5
done

# Wait for TektonConfig to be ready
echo "→ Waiting for TektonConfig to become Ready..."
for i in $(seq 1 90); do
  READY=$(oc get tektonconfig config -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "Waiting")
  if [ "$READY" = "True" ]; then
    VERSION=$(oc get tektonconfig config -o jsonpath='{.status.version}' 2>/dev/null || echo "unknown")
    echo "✓ TektonConfig ready (version: $VERSION)"
    break
  fi
  [ "$i" -eq 90 ] && { echo "✗ Timeout waiting for TektonConfig (status: $READY)"; exit 1; }
  sleep 5
done

echo ""
echo "=== Installation Complete ==="
echo "Run verify.sh to confirm health, or apply project Tekton resources:"
echo "  oc apply -f openshift/tekton/04-rbac.yaml"
echo "  oc apply -f openshift/tekton/01-tasks.yaml"
echo "  oc apply -f openshift/tekton/03-pipeline.yaml"
