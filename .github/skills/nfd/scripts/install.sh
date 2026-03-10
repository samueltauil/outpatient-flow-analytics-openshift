#!/usr/bin/env bash
# Install Node Feature Discovery (NFD) operator via OLM
# Idempotent — safe to re-run.
set -euo pipefail

echo "=== Node Feature Discovery Operator Install ==="

CHANNEL="${1:-stable}"
NFD_IMAGE="${2:-registry.redhat.io/openshift4/ose-node-feature-discovery-rhel9:v4.20}"

# Step 1: Namespace
if oc get namespace openshift-nfd &>/dev/null; then
  echo "✓ Namespace openshift-nfd exists"
else
  echo "→ Creating namespace..."
  oc apply -f - <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: openshift-nfd
  labels:
    openshift.io/cluster-monitoring: "true"
  annotations:
    openshift.io/display-name: "Node Feature Discovery Operator"
EOF
fi

# Step 2: OperatorGroup
if oc get operatorgroup nfd-group -n openshift-nfd &>/dev/null; then
  echo "✓ OperatorGroup exists"
else
  echo "→ Creating OperatorGroup..."
  oc apply -f - <<EOF
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: nfd-group
  namespace: openshift-nfd
spec:
  targetNamespaces:
    - openshift-nfd
EOF
fi

# Step 3: Subscription
if oc get subscription nfd -n openshift-nfd &>/dev/null; then
  CURRENT=$(oc get subscription nfd -n openshift-nfd \
    -o jsonpath='{.status.currentCSV}' 2>/dev/null || echo "pending")
  echo "✓ Subscription already exists (CSV: $CURRENT)"
else
  echo "→ Creating Subscription (channel: $CHANNEL)..."
  oc apply -f - <<EOF
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: nfd
  namespace: openshift-nfd
spec:
  channel: ${CHANNEL}
  installPlanApproval: Automatic
  name: nfd
  source: redhat-operators
  sourceNamespace: openshift-marketplace
EOF
  echo "✓ Subscription created"
fi

# Wait for CSV
echo "→ Waiting for CSV to reach Succeeded phase..."
for i in $(seq 1 60); do
  PHASE=$(oc get csv -n openshift-nfd -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "Waiting")
  if [ "$PHASE" = "Succeeded" ]; then
    CSV=$(oc get csv -n openshift-nfd -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    echo "✓ CSV ready: $CSV"
    break
  fi
  [ "$i" -eq 60 ] && { echo "✗ Timeout waiting for CSV (last phase: $PHASE)"; exit 1; }
  sleep 5
done

# Step 4: RBAC
echo "→ Creating RBAC resources..."
oc apply -f - <<'EOF'
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: nfd-master-nodefeature-reader
rules:
  - apiGroups: ["nfd.k8s-sigs.io"]
    resources: ["nodefeatures"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: nfd-master-nodefeaturerules-reader
rules:
  - apiGroups: ["nfd.k8s-sigs.io"]
    resources: ["nodefeaturerules"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: nfd-nodefeature-writer
rules:
  - apiGroups: ["nfd.k8s-sigs.io"]
    resources: ["nodefeatures"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: nfd-master-nodefeature-access
subjects:
  - kind: ServiceAccount
    name: nfd-master
    namespace: openshift-nfd
roleRef:
  kind: ClusterRole
  name: nfd-master-nodefeature-reader
  apiGroup: rbac.authorization.k8s.io
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: nfd-master-nodefeaturerules-access
subjects:
  - kind: ServiceAccount
    name: nfd-master
    namespace: openshift-nfd
roleRef:
  kind: ClusterRole
  name: nfd-master-nodefeaturerules-reader
  apiGroup: rbac.authorization.k8s.io
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: nfd-worker-nodefeature-write-access
subjects:
  - kind: ServiceAccount
    name: nfd-worker
    namespace: openshift-nfd
roleRef:
  kind: ClusterRole
  name: nfd-nodefeature-writer
  apiGroup: rbac.authorization.k8s.io
EOF
echo "✓ RBAC created"

# Step 5: NodeFeatureDiscovery instance
if oc get nodefeaturediscovery nfd-instance -n openshift-nfd &>/dev/null; then
  echo "✓ NodeFeatureDiscovery instance already exists"
else
  echo "→ Creating NodeFeatureDiscovery instance..."
  oc apply -f - <<EOF
apiVersion: nfd.openshift.io/v1
kind: NodeFeatureDiscovery
metadata:
  name: nfd-instance
  namespace: openshift-nfd
spec:
  operand:
    image: ${NFD_IMAGE}
    imagePullPolicy: IfNotPresent
    servicePort: 12000
  topologyUpdater: false
  workerConfig:
    configData: |
      core:
        sleepInterval: 60s
      sources:
        pci:
          deviceClassWhitelist:
            - "0200"
            - "03"
            - "12"
          deviceLabelFields:
            - "vendor"
EOF
  echo "✓ NodeFeatureDiscovery instance created"
fi

# Wait for NFD workers to start
echo "→ Waiting for NFD worker pods..."
for i in $(seq 1 60); do
  WORKERS=$(oc get pods -n openshift-nfd -l app=nfd-worker --no-headers 2>/dev/null | grep -c Running || echo "0")
  if [ "$WORKERS" -gt 0 ]; then
    echo "✓ $WORKERS NFD worker pod(s) running"
    break
  fi
  [ "$i" -eq 60 ] && { echo "⚠ No NFD workers running yet — they may still be starting"; break; }
  sleep 5
done

echo ""
echo "=== Installation Complete ==="
echo "Run verify.sh to check node labels."
echo "GPU nodes should show: feature.node.kubernetes.io/pci-10de.present=true"
