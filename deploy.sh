#!/usr/bin/env bash
# =============================================================================
# Automated OpenShift Deployment — Outpatient Flow Analytics
#
# This script deploys the complete Outpatient Flow Analytics stack to an
# OpenShift cluster with GPU support. It is:
#   • IDEMPOTENT:  safe to re-run (uses oc apply, dry-run secrets)
#   • ADDITIVE:    never deletes namespaces or existing data
#   • SELF-HEALING: validates each step before proceeding
#
# Prerequisites:
#   - oc CLI logged in (cluster-admin or namespace-admin)
#   - OpenShift Pipelines (Tekton) operator installed
#   - NVIDIA GPU operator installed (for GPU analytics)
#   - Python 3 available on the host (for password generation)
#
# Usage:
#   ./deploy.sh                           # Full deployment
#   ./deploy.sh --skip-data               # Skip data generator + ETL seeding
#   ./deploy.sh --skip-tekton             # Skip Tekton pipeline setup
#   ./deploy.sh --skip-dcgm               # Skip DCGM ServiceMonitor
#   ./deploy.sh --run-pipeline            # Also trigger a pipeline run at the end
#   ./deploy.sh --dry-run                 # Validate manifests without applying
#
# Lessons encoded in this script:
#   1. RHEL PostgreSQL does NOT auto-execute init SQL — schema applied via oc exec
#   2. RAPIDS image needs nonroot-v2 SCC + runAsUser:1001 (conda group)
#   3. Tekton v1 uses computeResources, not resources (silently ignored otherwise)
#   4. Network policies must allow Tekton pods (namespace selector, not app labels)
#   5. analytics-output-pvc (RWO) binds to GPU node — report-viewer must co-locate
#   6. DCGM exporter needs a ServiceMonitor for Prometheus scraping
#   7. Data generator writes CSV only — explicit DB loading required
# =============================================================================
set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OC_DIR="${SCRIPT_DIR}/openshift"
DB_DIR="${SCRIPT_DIR}/db"
TEKTON_DIR="${OC_DIR}/tekton"

EDGE_NS="edge-collector"
CENTRAL_NS="central-analytics"
GPU_OPERATOR_NS="nvidia-gpu-operator"

SKIP_DATA=false
SKIP_TEKTON=false
SKIP_DCGM=false
RUN_PIPELINE=false
DRY_RUN=false

# Parse flags
for arg in "$@"; do
  case "$arg" in
    --skip-data)    SKIP_DATA=true ;;
    --skip-tekton)  SKIP_TEKTON=true ;;
    --skip-dcgm)    SKIP_DCGM=true ;;
    --run-pipeline) RUN_PIPELINE=true ;;
    --dry-run)      DRY_RUN=true ;;
    --help|-h)
      head -35 "$0" | tail -30
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg (use --help)" >&2
      exit 1
      ;;
  esac
done

# ─── Terminal colors ──────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[ OK ]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()    { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }
step()    { echo -e "\n${CYAN}${BOLD}═══ Step $1 ═══${NC}"; }
dryrun()  { if $DRY_RUN; then info "(dry-run) $*"; return 0; fi; return 1; }

# Wrapper: apply or validate
apply_manifest() {
  if $DRY_RUN; then
    oc apply --dry-run=server -f "$1" 2>&1 | head -5
  else
    oc apply -f "$1"
  fi
}

# Wait for a resource with timeout
wait_for() {
  local kind="$1" name="$2" ns="$3" condition="$4" timeout="${5:-180s}"
  if $DRY_RUN; then
    info "(dry-run) Would wait for ${kind}/${name} in ${ns}"
    return 0
  fi
  info "Waiting for ${kind}/${name} in ${ns} (timeout: ${timeout})..."
  if ! oc wait --for="${condition}" "${kind}/${name}" -n "${ns}" --timeout="${timeout}"; then
    warn "${kind}/${name} did not reach ${condition} within ${timeout}"
    warn "Debug: oc get ${kind}/${name} -n ${ns} -o yaml"
    return 1
  fi
  ok "${kind}/${name} is ready"
}

# Generate a cryptographically random password
gen_password() {
  python3 -c "import secrets,string; print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(24)))"
}

# ─── Pre-flight Checks ───────────────────────────────────────────────────────
step "0/12: Pre-flight checks"

info "Checking oc login..."
oc whoami > /dev/null 2>&1 || fail "Not logged in to OpenShift. Run 'oc login' first."
CLUSTER=$(oc whoami --show-server)
USER=$(oc whoami)
ok "Logged in as '${USER}' to ${CLUSTER}"

info "Checking cluster version..."
OCP_VERSION=$(oc get clusterversion version -o jsonpath='{.status.desired.version}' 2>/dev/null || echo "unknown")
ok "OpenShift ${OCP_VERSION}"

info "Checking for OpenShift Pipelines operator..."
if oc get crd pipelines.tekton.dev > /dev/null 2>&1; then
  TEKTON_VERSION=$(oc get tektonconfig -o jsonpath='{.items[0].status.version}' 2>/dev/null || echo "unknown")
  ok "OpenShift Pipelines ${TEKTON_VERSION} installed"
  HAS_TEKTON=true
else
  warn "OpenShift Pipelines operator not found — Tekton pipeline will be skipped"
  HAS_TEKTON=false
  SKIP_TEKTON=true
fi

info "Checking for NVIDIA GPU operator..."
if oc get namespace "${GPU_OPERATOR_NS}" > /dev/null 2>&1; then
  GPU_NODES=$(oc get nodes -l nvidia.com/gpu.present=true --no-headers 2>/dev/null | wc -l)
  ok "NVIDIA GPU operator found — ${GPU_NODES} GPU node(s) detected"
  HAS_GPU=true
else
  warn "NVIDIA GPU operator namespace not found — GPU analytics will use CPU fallback"
  HAS_GPU=false
  SKIP_DCGM=true
fi

info "Checking for required CLI tools..."
command -v python3 > /dev/null 2>&1 || fail "python3 is required for password generation"
ok "All pre-flight checks passed"

# ─── Step 1: Namespaces ──────────────────────────────────────────────────────
step "1/12: Namespaces"
apply_manifest "${OC_DIR}/00-namespaces.yaml"
ok "Namespaces: ${EDGE_NS}, ${CENTRAL_NS}"

# ─── Step 2: Secrets ─────────────────────────────────────────────────────────
step "2/12: Database secrets"

# Only generate new passwords if secrets don't exist yet
if oc get secret edge-db-credentials -n "${EDGE_NS}" > /dev/null 2>&1; then
  info "edge-db-credentials already exists — reusing (delete manually to regenerate)"
  EDGE_PW=$(oc get secret edge-db-credentials -n "${EDGE_NS}" -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d)
else
  EDGE_PW=$(gen_password)
  info "Generating new edge DB password"
fi

if oc get secret central-db-credentials -n "${CENTRAL_NS}" > /dev/null 2>&1; then
  info "central-db-credentials already exists — reusing"
  CENTRAL_PW=$(oc get secret central-db-credentials -n "${CENTRAL_NS}" -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d)
else
  CENTRAL_PW=$(gen_password)
  info "Generating new central DB password"
fi

if ! dryrun "Would create/update secrets"; then
  # Edge DB secret
  oc create secret generic edge-db-credentials \
    --from-literal=POSTGRES_DB=edge_collector \
    --from-literal=POSTGRES_USER=edge_user \
    --from-literal=POSTGRES_PASSWORD="${EDGE_PW}" \
    --from-literal=DATABASE_URL="postgresql://edge_user:${EDGE_PW}@edge-postgres:5432/edge_collector" \
    -n "${EDGE_NS}" --dry-run=client -o yaml | oc apply -f -

  # Central DB secret
  oc create secret generic central-db-credentials \
    --from-literal=POSTGRES_DB=central_analytics \
    --from-literal=POSTGRES_USER=central_user \
    --from-literal=POSTGRES_PASSWORD="${CENTRAL_PW}" \
    --from-literal=DATABASE_URL="postgresql://central_user:${CENTRAL_PW}@central-postgres:5432/central_analytics" \
    -n "${CENTRAL_NS}" --dry-run=client -o yaml | oc apply -f -

  # ETL cross-namespace credentials (central-analytics needs to reach edge-postgres)
  oc create secret generic edge-db-remote-credentials \
    --from-literal=EDGE_DB_HOST="edge-postgres.${EDGE_NS}.svc.cluster.local" \
    --from-literal=EDGE_DB_PORT="5432" \
    --from-literal=EDGE_DB_NAME=edge_collector \
    --from-literal=EDGE_DB_USER=edge_user \
    --from-literal=EDGE_DB_PASSWORD="${EDGE_PW}" \
    -n "${CENTRAL_NS}" --dry-run=client -o yaml | oc apply -f -

  # Label secrets for topology view
  for ns_secret in "${EDGE_NS}/edge-db-credentials" "${CENTRAL_NS}/central-db-credentials" "${CENTRAL_NS}/edge-db-remote-credentials"; do
    ns="${ns_secret%%/*}"; secret="${ns_secret##*/}"
    oc label secret "${secret}" -n "${ns}" app.kubernetes.io/part-of=hls-demo --overwrite 2>/dev/null || true
  done
fi
ok "Database secrets ready"

# ─── Step 3: ServiceAccounts ─────────────────────────────────────────────────
step "3/12: ServiceAccounts & RBAC"
apply_manifest "${OC_DIR}/09-service-accounts.yaml"

# SCC grants — required for RAPIDS GPU image (UID 1001 in conda group)
# nonroot-v2 allows running as a specific non-root UID
if ! $DRY_RUN; then
  for sa in gpu-analytics-sa; do
    if ! oc get scc nonroot-v2 -o json 2>/dev/null | grep -q "system:serviceaccount:${CENTRAL_NS}:${sa}"; then
      oc adm policy add-scc-to-user nonroot-v2 -z "${sa}" -n "${CENTRAL_NS}"
      ok "Granted nonroot-v2 SCC to ${sa}"
    else
      info "nonroot-v2 SCC already granted to ${sa}"
    fi
  done
fi
ok "ServiceAccounts and SCC grants ready"

# ─── Step 4: Resource Quotas & Limits ────────────────────────────────────────
step "4/12: Resource quotas & limit ranges"
apply_manifest "${OC_DIR}/10-resource-quotas.yaml"
ok "Resource quotas and limit ranges applied"

# ─── Step 5: ConfigMaps (DB init scripts) ────────────────────────────────────
step "5/12: Database init ConfigMaps"
if ! dryrun "Would create ConfigMaps from ${DB_DIR}/"; then
  oc create configmap edge-db-init --from-file="${DB_DIR}/" -n "${EDGE_NS}" --dry-run=client -o yaml | oc apply -f -
  oc create configmap central-db-init --from-file="${DB_DIR}/" -n "${CENTRAL_NS}" --dry-run=client -o yaml | oc apply -f -
fi
ok "DB init ConfigMaps ready"

# ─── Step 6: PostgreSQL Databases ────────────────────────────────────────────
step "6/12: PostgreSQL databases"
apply_manifest "${OC_DIR}/02-edge-postgres.yaml"
apply_manifest "${OC_DIR}/03-central-postgres.yaml"

if ! $DRY_RUN; then
  wait_for deployment edge-postgres "${EDGE_NS}" condition=available 180s
  wait_for deployment central-postgres "${CENTRAL_NS}" condition=available 180s

  # LESSON LEARNED: RHEL PostgreSQL image does NOT reliably auto-execute SQL
  # from /opt/app-root/src/postgresql-init/. We must apply schema explicitly.
  info "Applying database schema via oc exec (RHEL PostgreSQL init workaround)..."
  for ns_db in "${EDGE_NS}/edge-postgres" "${CENTRAL_NS}/central-postgres"; do
    ns="${ns_db%%/*}"; db="${ns_db##*/}"
    POD=$(oc get pods -n "${ns}" -l app="${db}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [ -z "${POD}" ]; then
      warn "No pod found for ${db} in ${ns} — schema will need manual application"
      continue
    fi

    # Check if schema already applied (idempotent)
    TABLE_COUNT=$(oc exec "${POD}" -n "${ns}" -- psql -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 2>/dev/null || echo "0")
    if [ "${TABLE_COUNT}" -ge 4 ]; then
      info "Schema already applied in ${db} (${TABLE_COUNT} tables) — skipping"
      continue
    fi

    info "Applying schema to ${db}..."
    oc exec "${POD}" -n "${ns}" -- psql -f /opt/app-root/src/postgresql-init/schema.sql 2>/dev/null || \
      oc exec -i "${POD}" -n "${ns}" -- psql < "${DB_DIR}/schema.sql"

    info "Applying seed data to ${db}..."
    oc exec "${POD}" -n "${ns}" -- psql -f /opt/app-root/src/postgresql-init/seed.sql 2>/dev/null || \
      oc exec -i "${POD}" -n "${ns}" -- psql < "${DB_DIR}/seed.sql"

    ok "Schema and seed data applied to ${db}"
  done
fi
ok "PostgreSQL databases ready with schema"

# ─── Step 7: Network Policies ────────────────────────────────────────────────
step "7/12: Network policies"
# LESSON LEARNED: Network policies must use namespace selectors (not pod labels)
# because Tekton pods get tekton.dev/* labels, NOT app-specific labels.
apply_manifest "${OC_DIR}/07-network-policies.yaml"
ok "Network policies applied"

# ─── Step 8: Data Generation & ETL ───────────────────────────────────────────
step "8/12: Data generation & ETL"

if $SKIP_DATA; then
  info "Skipping data generation (--skip-data)"
else
  if ! $DRY_RUN; then
    # Deploy data generator job
    apply_manifest "${OC_DIR}/04-data-generator-job.yaml"

    # Wait for job — data generator writes CSV only, not to PostgreSQL
    info "Waiting for data-generator job (generates CSV to PVC)..."
    if wait_for job data-generator "${EDGE_NS}" condition=complete 600s; then
      # LESSON LEARNED: Generator writes CSV only — we must load it into PostgreSQL
      info "Loading CSV data into edge PostgreSQL..."
      EDGE_POD=$(oc get pods -n "${EDGE_NS}" -l app=edge-postgres -o jsonpath='{.items[0].metadata.name}')
      GEN_POD=$(oc get pods -n "${EDGE_NS}" -l job-name=data-generator -o jsonpath='{.items[0].metadata.name}')

      # Check if there's already data
      ROW_COUNT=$(oc exec "${EDGE_POD}" -n "${EDGE_NS}" -- psql -tAc "SELECT count(*) FROM outpatient_case_event" 2>/dev/null || echo "0")
      if [ "${ROW_COUNT}" -gt 100 ]; then
        info "Edge DB already has ${ROW_COUNT} rows — skipping CSV load"
      else
        # Use a one-shot pod to load CSV via COPY
        info "Creating CSV loader job..."
        oc run csv-loader --rm -i --restart=Never \
          -n "${EDGE_NS}" \
          --image=ghcr.io/samueltauil/hls-data-generator:latest \
          --overrides="$(cat <<'LOADER_EOF'
{
  "spec": {
    "containers": [{
      "name": "csv-loader",
      "image": "ghcr.io/samueltauil/hls-data-generator:latest",
      "command": ["python3", "-c", "
import csv, os, psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cols = ['event_id','facility_id','procedure_type','scheduled_start_time','checkin_time','preop_start_time','op_start_time','postop_start_time','discharge_time','anesthesia_type','asa_class','case_status','created_at','source_generator_id']
sql = f\"INSERT INTO outpatient_case_event ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))}) ON CONFLICT DO NOTHING\"
with open('/data/cases.csv') as f:
    reader = csv.DictReader(f)
    batch, total = [], 0
    for row in reader:
        batch.append([row.get(c) or None for c in cols])
        if len(batch) >= 500:
            cur.executemany(sql, batch); conn.commit(); total += len(batch); batch = []
    if batch:
        cur.executemany(sql, batch); conn.commit(); total += len(batch)
print(f'Loaded {total} rows')
cur.close(); conn.close()
"],
      "envFrom": [{"secretRef": {"name": "edge-db-credentials"}}],
      "volumeMounts": [{"name": "data", "mountPath": "/data", "readOnly": true}]
    }],
    "volumes": [{"name": "data", "persistentVolumeClaim": {"claimName": "edge-data-pvc"}}],
    "restartPolicy": "Never"
  }
}
LOADER_EOF
)" --timeout=120s 2>/dev/null || warn "CSV loader may have failed — check edge DB manually"
        ROW_COUNT=$(oc exec "${EDGE_POD}" -n "${EDGE_NS}" -- psql -tAc "SELECT count(*) FROM outpatient_case_event" 2>/dev/null || echo "?")
        ok "Edge DB now has ${ROW_COUNT} rows"
      fi
    else
      warn "Data generator job did not complete — check: oc logs -f job/data-generator -n ${EDGE_NS}"
    fi
  else
    apply_manifest "${OC_DIR}/04-data-generator-job.yaml"
  fi
fi

# ETL CronJob (runs every 4 hours)
apply_manifest "${OC_DIR}/05-etl-cronjob.yaml"

if ! $SKIP_DATA && ! $DRY_RUN; then
  # Trigger an immediate ETL run to populate central DB
  info "Triggering initial ETL run..."
  oc create job etl-initial-run --from=cronjob/etl-edge-to-central -n "${CENTRAL_NS}" 2>/dev/null || \
    info "ETL initial run already exists"
  wait_for job etl-initial-run "${CENTRAL_NS}" condition=complete 120s || true
fi
ok "Data generation and ETL ready"

# ─── Step 9: GPU Analytics Job ───────────────────────────────────────────────
step "9/12: GPU analytics (standalone job)"
apply_manifest "${OC_DIR}/06-gpu-analytics-job.yaml"
ok "GPU analytics job manifest applied"

# ─── Step 10: Report Viewer ──────────────────────────────────────────────────
step "10/12: Report viewer"
# LESSON LEARNED: Report viewer shares analytics-output-pvc (RWO) with GPU job.
# The PVC binds to the GPU node on first use, so report-viewer must NOT have
# anti-affinity against GPU nodes.
apply_manifest "${OC_DIR}/08-report-viewer.yaml"
if ! $DRY_RUN; then
  wait_for deployment report-viewer "${CENTRAL_NS}" condition=available 120s || true
fi
ok "Report viewer deployed"

# ─── Step 11: Tekton Pipeline ────────────────────────────────────────────────
step "11/12: Tekton pipeline"

if $SKIP_TEKTON; then
  info "Skipping Tekton pipeline (--skip-tekton or operator not found)"
else
  apply_manifest "${TEKTON_DIR}/04-rbac.yaml"

  # Grant nonroot-v2 SCC to pipeline-sa (RAPIDS GPU image requires UID 1001)
  if ! $DRY_RUN; then
    if ! oc get scc nonroot-v2 -o json 2>/dev/null | grep -q "system:serviceaccount:${CENTRAL_NS}:pipeline-sa"; then
      oc adm policy add-scc-to-user nonroot-v2 -z pipeline-sa -n "${CENTRAL_NS}"
      ok "Granted nonroot-v2 SCC to pipeline-sa"
    fi
  fi

  # LESSON LEARNED: Tekton v1 uses 'computeResources' not 'resources' on steps.
  # The 'resources' field is silently ignored and LimitRange defaults apply instead.
  apply_manifest "${TEKTON_DIR}/01-tasks.yaml"
  apply_manifest "${TEKTON_DIR}/03-pipeline.yaml"

  if $RUN_PIPELINE && ! $DRY_RUN; then
    info "Triggering pipeline run..."
    RUN_NAME=$(oc create -f "${TEKTON_DIR}/05-pipelinerun.yaml" -n "${CENTRAL_NS}" -o jsonpath='{.metadata.name}' 2>/dev/null || echo "")
    if [ -n "${RUN_NAME}" ]; then
      ok "Pipeline run created: ${RUN_NAME}"
      info "Monitor: oc get pipelinerun ${RUN_NAME} -n ${CENTRAL_NS} -w"
    fi
  fi
  ok "Tekton pipeline ready"
fi

# ─── Step 12: DCGM ServiceMonitor ────────────────────────────────────────────
step "12/12: DCGM Prometheus integration"

if $SKIP_DCGM; then
  info "Skipping DCGM ServiceMonitor (--skip-dcgm or no GPU operator)"
else
  # LESSON LEARNED: DCGM exporter runs on port 9400 but OpenShift Prometheus
  # requires a ServiceMonitor to discover targets. The nvidia-gpu-operator
  # namespace already has openshift.io/cluster-monitoring: "true".
  if ! $DRY_RUN; then
    if oc get servicemonitor nvidia-dcgm-exporter -n "${GPU_OPERATOR_NS}" > /dev/null 2>&1; then
      info "DCGM ServiceMonitor already exists"
    else
      info "Creating DCGM ServiceMonitor..."
      cat <<EOF | oc apply -f -
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: nvidia-dcgm-exporter
  namespace: ${GPU_OPERATOR_NS}
  labels:
    app: nvidia-dcgm-exporter
spec:
  selector:
    matchLabels:
      app: nvidia-dcgm-exporter
  namespaceSelector:
    matchNames:
    - ${GPU_OPERATOR_NS}
  endpoints:
  - port: gpu-metrics
    interval: 15s
    path: /metrics
EOF
      ok "DCGM ServiceMonitor created — GPU metrics now flowing to Prometheus"
    fi
  fi
  ok "DCGM Prometheus integration ready"
fi

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  Deployment Complete!${NC}"
echo -e "${GREEN}${BOLD}═══════════════════════════════════════════════════════════════${NC}"
echo ""

if $DRY_RUN; then
  info "This was a dry run — no changes were made to the cluster"
  echo ""
fi

info "Deployed components:"
echo "  ├─ Namespaces:     ${EDGE_NS}, ${CENTRAL_NS}"
echo "  ├─ Databases:      edge-postgres, central-postgres (with schema + seed)"
echo "  ├─ Security:       6 ServiceAccounts, nonroot-v2 SCC, ResourceQuotas"
echo "  ├─ Network:        Cross-namespace policies (Tekton-aware)"
echo "  ├─ Jobs:           data-generator, gpu-analytics"
echo "  ├─ CronJobs:       etl-edge-to-central (every 4h)"
echo "  ├─ Services:       report-viewer (with Route)"
if ! $SKIP_TEKTON; then
  echo "  ├─ Tekton:         outpatient-analytics pipeline (3 stages)"
fi
if ! $SKIP_DCGM; then
  echo "  └─ Monitoring:     DCGM ServiceMonitor → Prometheus"
else
  echo "  └─ Monitoring:     (DCGM skipped)"
fi

echo ""
info "Report viewer URL:"
if ! $DRY_RUN; then
  oc get route report-viewer -n "${CENTRAL_NS}" -o jsonpath='  https://{.spec.host}{"\n"}' 2>/dev/null || echo "  (route not yet available)"
else
  echo "  (dry-run — route not queried)"
fi

echo ""
info "Quick commands:"
echo "  oc get pods -n ${EDGE_NS}                              # Edge namespace"
echo "  oc get pods -n ${CENTRAL_NS}                           # Central namespace"
echo "  oc get pipelinerun -n ${CENTRAL_NS}                    # Pipeline runs"
echo "  oc create -f openshift/tekton/05-pipelinerun.yaml      # Trigger pipeline"
echo ""
info "Cleanup (if needed — DESTRUCTIVE):"
echo "  oc delete namespace ${EDGE_NS} ${CENTRAL_NS}           # Remove everything"
echo ""
