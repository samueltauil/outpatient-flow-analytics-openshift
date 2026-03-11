# Cluster Provisioning Guide

This guide walks through provisioning an OpenShift cluster for the
**outpatient-flow-analytics** project. The process follows a 3-step GitOps
bootstrap that installs ArgoCD, GPU infrastructure, and Tekton pipelines,
then deploys the application stack via an ArgoCD app-of-apps.

---

## Prerequisites

| Requirement | Details |
|---|---|
| OpenShift cluster | 4.x with at least one NVIDIA GPU-capable worker node |
| `oc` CLI | Logged in as `cluster-admin` |
| Network access | GitHub (for `ocp-gpu-gitops` repo references) |
| Python 3 | Required by `deploy.sh` for password generation |

---

## Step 0 — Install ArgoCD Operator

Install the OpenShift GitOps operator and wait for the ArgoCD instance to
become available in the `openshift-gitops` namespace.

```bash
bash .github/skills/openshift-gitops/scripts/install.sh
bash .github/skills/openshift-gitops/scripts/verify.sh
```

The install script creates an OLM Subscription for
`openshift-gitops-operator` from the `redhat-operators` catalog, waits for
the CSV to reach the **Succeeded** phase, and confirms the ArgoCD server
deployment is **Available**.

> **Time:** ~5–10 minutes.

---

## Step 1 — Bootstrap GPU Infrastructure

Apply the **bigbang** ArgoCD Application from
[ocp-gpu-gitops](https://github.com/samueltauil/ocp-gpu-gitops). This uses
an app-of-apps pattern to deploy three components in order:

| Sync-wave | Component | Purpose |
|---|---|---|
| 2 | **NFD Operator** | Detects GPU hardware and labels worker nodes |
| 3 | **NVIDIA GPU Operator** | Installs drivers, device plugin, and container runtime |
| 4 | **DCGM Dashboard** | GPU telemetry visualization |

```bash
oc apply -f https://raw.githubusercontent.com/samueltauil/ocp-gpu-gitops/main/gitops/manifests/cluster/bootstrap/base/bigbang-app.yaml
```

### Monitor progress

```bash
# ArgoCD application status
oc get applications -n openshift-gitops

# Watch NFD pods come up
oc get pods -n openshift-nfd -w

# Watch GPU operator pods come up
oc get pods -n nvidia-gpu-operator -w
```

### Verify

```bash
bash .github/skills/nfd/scripts/verify.sh
bash .github/skills/nvidia-gpu/scripts/verify.sh
```

> **Time:** ~15–25 minutes. GPU driver compilation on the worker nodes is the
> slowest step.

---

## Step 2 — Install OpenShift Pipelines

Apply the ArgoCD Application that installs the Pipelines (Tekton) operator.
The application points at `openshift/operators/openshift-pipelines` in this
repository and uses `ServerSideApply` with `selfHeal: true`.

```bash
oc apply -f openshift/argocd/openshift-pipelines-app.yaml
```

### Verify

```bash
bash .github/skills/openshift-pipelines/scripts/verify.sh
```

> **Time:** ~10–15 minutes. The `TektonConfig` resource takes time to
> reconcile and stabilize.

---

## Step 3 — Deploy Application Stack via ArgoCD

After all operators are installed and healthy, deploy the application:

```bash
# Update placeholder secrets in openshift/01-secrets.yaml with real passwords before deploying

# Deploy application stack via ArgoCD app-of-apps
oc apply -f openshift/argocd/app-of-apps.yaml
```

This creates an app-of-apps that deploys 4 ArgoCD Applications in order:

| Application | Sync Wave | Components |
|------------|-----------|------------|
| `hls-shared-infra` | 1 | Namespaces, SCC RBAC, network policies, resource quotas |
| `hls-edge-collector` | 2 | Edge secrets, service accounts, PostgreSQL + DB init, data generator |
| `hls-central-analytics` | 3 | Central secrets, service accounts, PostgreSQL + DB init, ETL, GPU analytics, report viewer |
| `hls-tekton-pipeline` | 4 | Pipeline service account, Tekton tasks, pipeline |

Monitor progress:
```bash
oc get applications -n openshift-gitops
oc get pods -n edge-collector -w
oc get pods -n central-analytics -w
```

Verify databases initialized:
```bash
oc exec deploy/edge-postgres -n edge-collector -- psql -U postgres -d edge_collector -c '\dt'
oc exec deploy/central-postgres -n central-analytics -- psql -U postgres -d central_analytics -c '\dt'
```

### Triggering the Analytics Pipeline

PipelineRun is intentionally excluded from ArgoCD (it uses `generateName` and
would re-trigger on every sync). Trigger manually:

```bash
oc create -f openshift/tekton/05-pipelinerun.yaml -n central-analytics
```

Monitor pipeline execution:
```bash
oc get pipelineruns -n central-analytics -w
```

---

## Alternative: Deploy via deploy.sh (Non-GitOps Fallback)

If GitOps is not desired, deploy the full application stack directly:

```bash
./deploy.sh
```

`deploy.sh` is idempotent and additive—safe to re-run without data loss. It
performs the following steps:

1. Pre-flight checks (login, cluster version, operators)
2. Creates namespaces (`edge-collector`, `central-analytics`)
3. Generates database secrets (PostgreSQL credentials)
4. Configures ServiceAccounts, RBAC, and SCC grants
5. Applies resource quotas and limit ranges
6. Deploys PostgreSQL databases with schema initialization
7. Sets up network policies
8. Runs data generation and ETL jobs
9. Launches GPU analytics workload
10. Deploys the report viewer
11. Configures DCGM Prometheus ServiceMonitor

### Available flags

| Flag | Effect |
|---|---|
| `--skip-data` | Skip data generator and ETL seeding |
| `--skip-tekton` | Skip Tekton pipeline setup |
| `--skip-dcgm` | Skip DCGM ServiceMonitor configuration |
| `--run-pipeline` | Trigger a pipeline run after setup |
| `--dry-run` | Validate manifests without applying |
| `--help` | Show usage information |

---

## Verification Checklist

Run through this checklist after provisioning to confirm everything is
operational.

- [ ] **ArgoCD server running**
  ```bash
  oc get pods -n openshift-gitops -l app.kubernetes.io/name=openshift-gitops-server
  ```

- [ ] **NFD workers running**
  ```bash
  oc get pods -n openshift-nfd -l app=nfd-worker
  ```

- [ ] **GPU nodes labeled**
  ```bash
  oc get nodes -l feature.node.kubernetes.io/pci-10de.present=true
  ```

- [ ] **GPU drivers loaded**
  ```bash
  oc get pods -n nvidia-gpu-operator -l openshift.driver-toolkit=true
  ```

- [ ] **Pipelines ready**
  ```bash
  oc get tektonconfig config -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
  ```

- [ ] **nvidia-smi works**
  ```bash
  oc exec -n nvidia-gpu-operator \
    $(oc get pods -n nvidia-gpu-operator -l openshift.driver-toolkit=true -o name | head -1) \
    -- nvidia-smi
  ```

---

## Non-GitOps Fallback

For clusters where GitOps is not desired, each operator can be installed
directly using the skill scripts. Run them in dependency order:

```bash
# 1. ArgoCD (optional when not using GitOps, but scripts live here)
bash .github/skills/openshift-gitops/scripts/install.sh

# 2. Pipelines — independent, can install anytime
bash .github/skills/openshift-pipelines/scripts/install.sh

# 3. NFD — must complete before GPU Operator
bash .github/skills/nfd/scripts/install.sh

# 4. GPU Operator — depends on NFD node labels
bash .github/skills/nvidia-gpu/scripts/install.sh
```

> **Dependency order:** ArgoCD → Pipelines *(independent)* → NFD → GPU Operator

After all operators are installed, deploy the application stack with
`./deploy.sh` as described in the [Alternative: Deploy via deploy.sh](#alternative-deploy-via-deploysh-non-gitops-fallback) section.

---

## Troubleshooting Quick Reference

Each operator has a dedicated agent skill with a comprehensive guide, health
check script, and CRD reference tool.

| Issue | Skill to use |
|---|---|
| ArgoCD sync failures | `openshift-gitops` |
| Missing GPU node labels | `nfd` |
| GPU driver or scheduling issues | `nvidia-gpu` |
| Pipeline or task failures | `openshift-pipelines` |

Every skill directory (`.github/skills/<name>/`) provides:

| File | Purpose |
|---|---|
| `SKILL.md` | Full installation and troubleshooting guide |
| `scripts/verify.sh` | Automated health check (exit 0 = healthy) |
| `scripts/install.sh` | Idempotent operator installation |
| `scripts/lookup-crd.sh` | Query CRD field details from OpenAPI schemas |
| `references/crd-summary.md` | Quick-reference CRD field overview |
