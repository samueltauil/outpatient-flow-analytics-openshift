# Copilot Instructions

## OpenShift Operator Skills

This project includes agent skills for installing, configuring, and troubleshooting OpenShift operators.
When the user asks about installing, configuring, fixing, or troubleshooting any of the operators below,
read the corresponding `SKILL.md` for full instructions and use the bundled `scripts/` for execution.

### Available skills

| Skill | Path | Use when |
|-------|------|----------|
| **OpenShift Pipelines** | `.github/skills/openshift-pipelines/` | Installing/configuring Tekton, pipelines, tasks, triggers |
| **OpenShift GitOps** | `.github/skills/openshift-gitops/` | Installing/configuring ArgoCD, Applications, GitOps sync |
| **Node Feature Discovery** | `.github/skills/nfd/` | Installing NFD, GPU node labeling, hardware detection |
| **NVIDIA GPU Operator** | `.github/skills/nvidia-gpu/` | Installing GPU operator, ClusterPolicy, DCGM, driver issues |

### How to use the skills

1. **Read the SKILL.md** in the matching skill directory to understand the full procedure.
2. **Run `scripts/install.sh`** to install the operator. The script is idempotent — safe to re-run.
3. **Run `scripts/verify.sh`** to check health. Returns exit code 0 if healthy, non-zero with diagnostics if not.
4. **Run `scripts/lookup-crd.sh <crd> [field.path]`** to query detailed CRD field info (types, enums, defaults, nested fields) from the full OpenAPI schemas in `openshift/crds/`.
5. **Read `references/crd-summary.md`** for a quick overview of CRD fields.
6. **Full CRD schemas** are in `openshift/crds/` if you need the raw YAML.

### Operator dependency order

When installing multiple operators, follow this order:

```
1. OpenShift GitOps     (if using GitOps-based install)
2. OpenShift Pipelines  (independent, can install anytime)
3. NFD                  (must be before GPU operator)
4. NVIDIA GPU Operator  (depends on NFD labels)
```

Or use the GitOps bootstrap to install NFD + GPU together:
```bash
oc apply -f https://raw.githubusercontent.com/samueltauil/ocp-gpu-gitops/main/gitops/manifests/cluster/bootstrap/base/bigbang-app.yaml
```

### Project context

This is the **outpatient-flow-analytics** project. Key things to know:
- GPU workloads use NVIDIA RAPIDS images that run as UID 1001 — they need `nonroot-v2` SCC.
- Tekton v1 API requires `computeResources` not `resources` in task steps (silently ignored otherwise).
- Non-GPU pods use `nvidia.com/gpu.present DoesNotExist` anti-affinity to avoid GPU nodes.
- The project deploys across two namespaces: `edge-collector` and `central-analytics`.
