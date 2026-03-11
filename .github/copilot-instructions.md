# Copilot Instructions

## OpenShift Operator Skills

This project includes agent skills for troubleshooting, configuring, and diagnosing OpenShift operators.
Operator installation is primarily handled by the **ocp-gpu-gitops** bootstrap workflow (ArgoCD).
When the user asks about configuring, fixing, or troubleshooting any of the operators below,
read the corresponding `SKILL.md` for full instructions and use the bundled `scripts/` for execution.

### Available skills

| Skill | Path | Use when |
|-------|------|----------|
| **OpenShift Pipelines** | `.github/skills/openshift-pipelines/` | Troubleshooting Tekton pipelines, tasks, SCC, TektonConfig issues. Also handles installation via ArgoCD Application. |
| **OpenShift GitOps** | `.github/skills/openshift-gitops/` | Installing ArgoCD (Step 0 bootstrap), troubleshooting sync failures, drift, Application health |
| **Node Feature Discovery** | `.github/skills/nfd/` | Troubleshooting GPU node labeling, missing labels, worker pod issues. Installed by ocp-gpu-gitops. |
| **NVIDIA GPU Operator** | `.github/skills/nvidia-gpu/` | Troubleshooting GPU drivers, ClusterPolicy, DCGM, SCC issues. Installed by ocp-gpu-gitops. |

### How to use the skills

0. **For new cluster provisioning**, follow the guide in `docs/cluster-provisioning.md`.
1. **Read the SKILL.md** in the matching skill directory to understand the full procedure.
2. **Run `scripts/verify.sh`** to check health — this is the first step for any troubleshooting. Returns exit code 0 if healthy, non-zero with diagnostics if not.
3. **Run `scripts/install.sh`** as a fallback for non-GitOps installs. The script is idempotent — safe to re-run.
4. **Run `scripts/lookup-crd.sh <crd> [field.path]`** to query detailed CRD field info (types, enums, defaults, nested fields) from the full OpenAPI schemas in `openshift/crds/`.
5. **Read `references/crd-summary.md`** for a quick overview of CRD fields.
6. **Full CRD schemas** are in `openshift/crds/` if you need the raw YAML.

### Cluster Bootstrap Workflow

For new clusters, follow this sequence:

1. Install ArgoCD operator:
   ```bash
   bash .github/skills/openshift-gitops/scripts/install.sh
   ```

2. Bootstrap GPU infrastructure (NFD + GPU Operator + DCGM):
   ```bash
   oc apply -f https://raw.githubusercontent.com/samueltauil/ocp-gpu-gitops/main/gitops/manifests/cluster/bootstrap/base/bigbang-app.yaml
   ```

3. Install OpenShift Pipelines:
   ```bash
   oc apply -f openshift/argocd/openshift-pipelines-app.yaml
   ```

See `docs/cluster-provisioning.md` for the full guide.

### Fallback: Direct Installation

If not using GitOps, install operators directly in this order:

```
1. OpenShift GitOps     (if using GitOps-based install)
2. OpenShift Pipelines  (independent, can install anytime)
3. NFD                  (must be before GPU operator)
4. NVIDIA GPU Operator  (depends on NFD labels)
```

### Project context

This is the **outpatient-flow-analytics** project. Key things to know:
- GPU workloads use NVIDIA RAPIDS images that run as UID 1001 — they need `nonroot-v2` SCC.
- Tekton v1 API requires `computeResources` not `resources` in task steps (silently ignored otherwise).
- Non-GPU pods use `nvidia.com/gpu.present DoesNotExist` anti-affinity to avoid GPU nodes.
- The project deploys across two namespaces: `edge-collector` and `central-analytics`.
