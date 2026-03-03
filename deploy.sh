#!/usr/bin/env bash
# =============================================================================
# Safe OpenShift Deployment Script — Outpatient Flow Analytics
# ADDITIVE ONLY: uses oc apply / oc create (never oc delete namespace)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OC_DIR="${SCRIPT_DIR}/openshift"
DB_DIR="${SCRIPT_DIR}/db"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

# Pre-flight checks
info "Pre-flight checks..."
oc whoami > /dev/null 2>&1 || fail "Not logged in to OpenShift. Run 'oc login' first."
CLUSTER=$(oc whoami --show-server)
USER=$(oc whoami)
ok "Logged in as '${USER}' to ${CLUSTER}"

# ─── Step 1: Namespaces ──────────────────────────────────────────────────────
info "Step 1/9: Creating namespaces..."
oc apply -f "${OC_DIR}/00-namespaces.yaml"
ok "Namespaces ready"

# ─── Step 2: Generate and apply secrets with random passwords ─────────────────
info "Step 2/9: Creating secrets with generated passwords..."
EDGE_PW=$(python3 -c "import secrets,string; print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(24)))")
CENTRAL_PW=$(python3 -c "import secrets,string; print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(24)))")

# Edge DB secret
oc create secret generic edge-db-credentials \
  --from-literal=POSTGRES_DB=edge_collector \
  --from-literal=POSTGRES_USER=edge_user \
  --from-literal=POSTGRES_PASSWORD="${EDGE_PW}" \
  --from-literal=DATABASE_URL="postgresql://edge_user:${EDGE_PW}@edge-postgres:5432/edge_collector" \
  -n edge-collector --dry-run=client -o yaml | \
  oc apply -f -

# Central DB secret
oc create secret generic central-db-credentials \
  --from-literal=POSTGRES_DB=central_analytics \
  --from-literal=POSTGRES_USER=central_user \
  --from-literal=POSTGRES_PASSWORD="${CENTRAL_PW}" \
  --from-literal=DATABASE_URL="postgresql://central_user:${CENTRAL_PW}@central-postgres:5432/central_analytics" \
  -n central-analytics --dry-run=client -o yaml | \
  oc apply -f -

# ETL cross-namespace credentials
oc create secret generic edge-db-remote-credentials \
  --from-literal=EDGE_DB_HOST="edge-postgres.edge-collector.svc.cluster.local" \
  --from-literal=EDGE_DB_PORT="5432" \
  --from-literal=EDGE_DB_NAME=edge_collector \
  --from-literal=EDGE_DB_USER=edge_user \
  --from-literal=EDGE_DB_PASSWORD="${EDGE_PW}" \
  -n central-analytics --dry-run=client -o yaml | \
  oc apply -f -

# Label all secrets
for ns_secret in "edge-collector/edge-db-credentials" "central-analytics/central-db-credentials" "central-analytics/edge-db-remote-credentials"; do
  ns="${ns_secret%%/*}"
  secret="${ns_secret##*/}"
  oc label secret "${secret}" -n "${ns}" app.kubernetes.io/part-of=hls-demo --overwrite 2>/dev/null || true
done
ok "Secrets created with random passwords"

# ─── Step 3: ServiceAccounts and ResourceQuotas ──────────────────────────────
info "Step 3/9: Creating ServiceAccounts and ResourceQuotas..."
oc apply -f "${OC_DIR}/09-service-accounts.yaml"
oc apply -f "${OC_DIR}/10-resource-quotas.yaml"
ok "ServiceAccounts and ResourceQuotas applied"

# ─── Step 4: ConfigMaps from DB schema ────────────────────────────────────────
info "Step 4/9: Creating DB init ConfigMaps..."
oc create configmap edge-db-init --from-file="${DB_DIR}/" -n edge-collector --dry-run=client -o yaml | \
  oc apply -f -
oc create configmap central-db-init --from-file="${DB_DIR}/" -n central-analytics --dry-run=client -o yaml | \
  oc apply -f -
ok "DB init ConfigMaps ready"

# ─── Step 5: Deploy databases ────────────────────────────────────────────────
info "Step 5/9: Deploying PostgreSQL instances..."
oc apply -f "${OC_DIR}/02-edge-postgres.yaml"
oc apply -f "${OC_DIR}/03-central-postgres.yaml"

info "Waiting for edge-postgres..."
oc wait --for=condition=available deployment/edge-postgres -n edge-collector --timeout=180s
ok "Edge PostgreSQL is ready"

info "Waiting for central-postgres..."
oc wait --for=condition=available deployment/central-postgres -n central-analytics --timeout=180s
ok "Central PostgreSQL is ready"

# ─── Step 6: Network policies ────────────────────────────────────────────────
info "Step 6/9: Applying network policies..."
oc apply -f "${OC_DIR}/07-network-policies.yaml"
ok "Network policies applied"

# ─── Step 7: Seed edge DB ────────────────────────────────────────────────────
info "Step 7/9: Running data generator job..."
oc apply -f "${OC_DIR}/04-data-generator-job.yaml"
info "Waiting for data-generator job to complete (this may take a few minutes)..."
oc wait --for=condition=complete job/data-generator -n edge-collector --timeout=600s || \
  warn "Data generator job did not complete within timeout — check logs with: oc logs -f job/data-generator -n edge-collector"
ok "Data generator job submitted"

# ─── Step 8: ETL CronJob ─────────────────────────────────────────────────────
info "Step 8/9: Deploying ETL CronJob..."
oc apply -f "${OC_DIR}/05-etl-cronjob.yaml"
ok "ETL CronJob deployed (schedule: 0 */4 * * *)"

# ─── Step 9: GPU Analytics + Report Viewer ───────────────────────────────────
info "Step 9/9: Deploying GPU analytics and report viewer..."
oc apply -f "${OC_DIR}/06-gpu-analytics-job.yaml"
oc apply -f "${OC_DIR}/08-report-viewer.yaml"

info "Waiting for report-viewer..."
oc wait --for=condition=available deployment/report-viewer -n central-analytics --timeout=120s || \
  warn "Report viewer not yet ready — check: oc get pods -n central-analytics"
ok "Report viewer deployed"

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo ""
info "Resources deployed:"
echo "  Namespaces:     edge-collector, central-analytics"
echo "  Databases:      edge-postgres, central-postgres"
echo "  Jobs:           data-generator (completed), gpu-analytics (running)"
echo "  CronJobs:       etl-edge-to-central (every 4h)"
echo "  Services:       report-viewer (with Route)"
echo ""
info "Report viewer URL:"
oc get route report-viewer -n central-analytics -o jsonpath='  https://{.spec.host}{"\n"}' 2>/dev/null || echo "  (route not yet available)"
echo ""
info "Quick verification commands:"
echo "  oc get pods -n edge-collector"
echo "  oc get pods -n central-analytics"
echo "  oc get cronjob -n central-analytics"
echo "  oc get route -n central-analytics"
