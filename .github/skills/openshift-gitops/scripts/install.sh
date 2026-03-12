#!/usr/bin/env bash
# Install OpenShift GitOps (ArgoCD) operator via OLM
# Idempotent — safe to re-run.
set -euo pipefail

echo "=== OpenShift GitOps Operator Install ==="

CHANNEL="${1:-latest}"

# Check if already installed
if oc get subscription openshift-gitops-operator -n openshift-operators &>/dev/null; then
  CURRENT=$(oc get subscription openshift-gitops-operator -n openshift-operators \
    -o jsonpath='{.status.currentCSV}' 2>/dev/null || echo "pending")
  echo "✓ Subscription already exists (CSV: $CURRENT)"
else
  echo "→ Creating Subscription (channel: $CHANNEL)..."
  oc apply -f - <<EOF
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: openshift-gitops-operator
  namespace: openshift-operators
spec:
  channel: ${CHANNEL}
  installPlanApproval: Automatic
  name: openshift-gitops-operator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
EOF
  echo "✓ Subscription created"
fi

# Wait for CSV
echo "→ Waiting for CSV to reach Succeeded phase..."
for i in $(seq 1 60); do
  PHASE=$(oc get csv -n openshift-gitops -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "Waiting")
  if [ "$PHASE" = "Succeeded" ]; then
    CSV=$(oc get csv -n openshift-gitops -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    echo "✓ CSV ready: $CSV"
    break
  fi
  [ "$i" -eq 60 ] && { echo "✗ Timeout waiting for CSV (last phase: $PHASE)"; exit 1; }
  sleep 5
done

# Wait for ArgoCD server deployment
echo "→ Waiting for ArgoCD server to become Available..."
for i in $(seq 1 60); do
  AVAIL=$(oc get deployment openshift-gitops-server -n openshift-gitops \
    -o jsonpath='{.status.conditions[?(@.type=="Available")].status}' 2>/dev/null || echo "Waiting")
  if [ "$AVAIL" = "True" ]; then
    echo "✓ ArgoCD server is available"
    break
  fi
  [ "$i" -eq 60 ] && { echo "✗ Timeout waiting for ArgoCD server"; exit 1; }
  sleep 5
done

# Grant ArgoCD application controller cluster-admin so it can manage
# CRDs like NodeFeatureDiscovery and ClusterPolicy across namespaces.
APP_CONTROLLER_SA="system:serviceaccount:openshift-gitops:openshift-gitops-argocd-application-controller"
if oc get clusterrolebinding openshift-gitops-argocd-controller-cluster-admin &>/dev/null; then
  echo "✓ App controller cluster-admin already granted"
else
  echo "→ Granting cluster-admin to ArgoCD application controller..."
  oc create clusterrolebinding openshift-gitops-argocd-controller-cluster-admin \
    --clusterrole=cluster-admin \
    --serviceaccount=openshift-gitops:openshift-gitops-argocd-application-controller
  echo "✓ App controller cluster-admin granted"
fi

# Enable kustomize cross-directory references (required by app kustomizations
# that reference shared manifests via ../../ paths).
CURRENT_OPTS=$(oc get argocd openshift-gitops -n openshift-gitops \
  -o jsonpath='{.spec.kustomizeBuildOptions}' 2>/dev/null || echo "")
if echo "$CURRENT_OPTS" | grep -q "LoadRestrictionsNone"; then
  echo "✓ Kustomize build options already configured"
else
  echo "→ Configuring kustomize --load-restrictor LoadRestrictionsNone..."
  oc patch argocd openshift-gitops -n openshift-gitops --type merge \
    -p '{"spec":{"kustomizeBuildOptions":"--load-restrictor LoadRestrictionsNone"}}'
  echo "✓ Kustomize build options configured"
fi

# Print access info
ROUTE=$(oc get route openshift-gitops-server -n openshift-gitops \
  -o jsonpath='{.spec.host}' 2>/dev/null || echo "route not found")

echo ""
echo "=== Installation Complete ==="
echo "ArgoCD URL: https://$ROUTE"
echo ""
echo "To label namespaces for ArgoCD management:"
echo "  oc label namespace <ns> argocd.argoproj.io/managed-by=openshift-gitops"
echo ""
echo "To bootstrap GPU infra via GitOps:"
echo "  oc apply -f https://raw.githubusercontent.com/samueltauil/ocp-gpu-gitops/main/gitops/manifests/cluster/bootstrap/base/bigbang-app.yaml"
