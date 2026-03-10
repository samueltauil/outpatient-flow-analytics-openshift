# OpenShift GitOps CRD Field Reference

Full CRD schemas are in `openshift/crds/openshift-gitops-operator/`.

## ArgoCD (argoproj.io/v1beta1)

Defines an ArgoCD instance with all its components.

**Key spec fields:**
- `spec.server.route.enabled` — Expose ArgoCD via OpenShift Route
- `spec.server.route.tls.termination` — `edge`, `passthrough`, `reencrypt`
- `spec.server.insecure` — Disable TLS (not recommended for prod)
- `spec.controller.resources` — Controller resource requests/limits
- `spec.controller.sharding.enabled` — Enable controller sharding for large clusters
- `spec.repo.resources` — Repo server resource requests/limits
- `spec.ha.enabled` — High availability mode
- `spec.rbac.defaultPolicy` — Default RBAC policy (`role:readonly`, `role:admin`)
- `spec.rbac.policy` — Custom RBAC policy (CSV format)
- `spec.rbac.scopes` — OIDC scopes for RBAC (e.g. `[groups]`)
- `spec.resourceExclusions` — Resources to exclude from tracking (e.g. TaskRuns, PipelineRuns)
- `spec.resourceInclusions` — Resources to explicitly include
- `spec.sso.provider` — SSO provider (`dex`, `keycloak`)
- `spec.notifications.enabled` — Enable notifications controller

## Application (argoproj.io/v1alpha1)

Declares a desired state to sync from a Git source to a cluster destination.

**Key spec fields:**
- `spec.project` — AppProject name (default: `default`)
- `spec.source.repoURL` — Git repository URL
- `spec.source.path` — Path within the repo
- `spec.source.targetRevision` — Branch, tag, or commit SHA
- `spec.source.kustomize` — Kustomize overrides
- `spec.source.helm` — Helm chart overrides (values, parameters)
- `spec.destination.server` — Target cluster API URL
- `spec.destination.namespace` — Target namespace
- `spec.syncPolicy.automated.prune` — Auto-delete resources removed from Git
- `spec.syncPolicy.automated.selfHeal` — Auto-sync when drift detected
- `spec.syncPolicy.syncOptions` — `CreateNamespace=true`, `ServerSideApply=true`, `SkipDryRunOnMissingResource=true`

**Key annotations:**
- `argocd.argoproj.io/sync-wave` — Controls sync ordering (lower = earlier)
- `argocd.argoproj.io/compare-options: IgnoreExtraneous` — Ignore extra resources in target
- `argocd.argoproj.io/sync-options: SkipDryRunOnMissingResource=true` — Skip dry run for CRDs

## ApplicationSet (argoproj.io/v1alpha1)

Generates multiple Applications from templates using generators.

**Key spec fields:**
- `spec.generators` — List of generators (list, cluster, git, matrix, merge, pullRequest)
- `spec.generators[].list.elements` — Static list of values
- `spec.generators[].clusters` — One Application per cluster
- `spec.generators[].git.repoURL` — Generate from directories/files in a repo
- `spec.template` — Application template to fill with generator values
- `spec.syncPolicy.preserveResourcesOnDeletion` — Keep resources when ApplicationSet is deleted

## AppProject (argoproj.io/v1alpha1)

RBAC boundary for Applications — restricts what sources and destinations are allowed.

**Key spec fields:**
- `spec.sourceRepos` — Allowed Git repo URLs (wildcards supported)
- `spec.destinations` — Allowed cluster+namespace pairs
- `spec.clusterResourceWhitelist` — Allowed cluster-scoped resource types
- `spec.namespaceResourceBlacklist` — Denied namespace-scoped resource types
- `spec.roles` — Custom RBAC roles within the project
- `spec.orphanedResources.warn` — Warn on resources not tracked by any Application

## RolloutManager (argoproj.io/v1alpha1)

Manages Argo Rollouts controller for progressive delivery.

**Key spec fields:**
- `spec.env` — Environment variables for rollouts controller
- `spec.image` — Custom controller image
- `spec.version` — Controller version

## Rollout (argoproj.io/v1alpha1)

Progressive delivery — blue-green or canary deployment strategy.

**Key spec fields:**
- `spec.strategy.canary` — Canary deployment (steps, analysis, traffic management)
- `spec.strategy.blueGreen` — Blue-green deployment (preview, active services)
- `spec.selector` — Pod selector
- `spec.template` — Pod template (same as Deployment)

## NotificationsConfiguration (argoproj.io/v1alpha1)

Configures alerts for Application sync/health events.

**Key spec fields:**
- `spec.triggers` — When to send notifications
- `spec.templates` — Notification message templates
- `spec.services` — Notification backends (Slack, email, webhook)

## ImageUpdater (argocd-image-updater.argoproj.io/v1alpha1)

Auto-updates container image tags in Applications.

**Key spec fields:**
- `spec.image` — Image updater controller image
- `spec.logLevel` — Log verbosity
- `spec.registries` — Container registry configurations
