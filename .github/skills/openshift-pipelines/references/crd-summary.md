# OpenShift Pipelines CRD Field Reference

Full CRD schemas are in `openshift/crds/openshift-pipelines-operator-rh/`.

## TektonConfig (operator.tekton.dev)

The main configuration CR. Auto-created as `config` when the operator installs.

**Key spec fields:**
- `spec.profile` — `all` (default), `lite`, `basic`. Controls which components are deployed.
- `spec.targetNamespace` — Namespace for Tekton components (default: `openshift-pipelines`)
- `spec.pruner.keep` — Number of PipelineRuns/TaskRuns to retain
- `spec.pruner.schedule` — Cron schedule for pruning
- `spec.pruner.resources` — Resources to prune: `[pipelinerun, taskrun]`
- `spec.pipeline` — Pipeline controller settings (timeouts, feature flags)
- `spec.pipeline.default-timeout-minutes` — Default timeout for PipelineRuns
- `spec.pipeline.enable-api-fields` — `stable`, `beta`, `alpha`
- `spec.trigger` — Trigger controller settings
- `spec.chain` — Chains (supply chain security) settings
- `spec.chain.disabled` — `true`/`false`
- `spec.addon` — Addon settings (ClusterTasks, pipeline templates)
- `spec.hub` — Hub settings
- `spec.platforms.openshift.pipelinesAsCode.enable` — Enable Pipelines-as-Code

## TektonPipeline (operator.tekton.dev)

Controls the pipeline controller configuration. Usually managed via TektonConfig.

**Key spec fields:**
- `spec.enable-api-fields` — Feature gate level
- `spec.default-timeout-minutes` — Default PipelineRun timeout
- `spec.disable-affinity-assistant` — Disable workspace affinity assistant
- `spec.running-in-environment-with-injected-sidecars` — Handle sidecar injection

## TektonChain (operator.tekton.dev)

Supply chain security — signing, attestation, provenance.

**Key spec fields:**
- `spec.artifacts.taskrun.format` — Attestation format: `in-toto`, `tekton`
- `spec.artifacts.taskrun.storage` — Storage backend: `oci`, `tekton`, `gcs`
- `spec.artifacts.oci.format` — OCI artifact format
- `spec.transparency.enabled` — Enable transparency log (Rekor)
- `spec.signers.x509.fulcio.enabled` — Enable Fulcio for keyless signing

## TektonResult (operator.tekton.dev)

Long-term storage for PipelineRun/TaskRun results and logs.

**Key spec fields:**
- `spec.db_host`, `spec.db_port`, `spec.db_name` — Database connection
- `spec.server_port` — API server port
- `spec.log_level` — Logging level
- `spec.logs_api` — Enable/disable logs API
- `spec.logs_type` — Log storage type: `File`, `S3`, `GCS`
- `spec.logs_path` — Path for file-based log storage

## TektonPruner (operator.tekton.dev)

Auto-cleanup of old runs to prevent resource buildup.

**Key spec fields:**
- `spec.resources` — List of resources to prune
- `spec.keep` — Number of resources to keep
- `spec.schedule` — Cron schedule
- `spec.namespace` — Target namespace (empty = all)

## ManualApprovalGate (operator.tekton.dev)

Adds manual approval steps to pipelines.

**Key spec fields:**
- `spec.approvers` — List of approved users/groups
- `spec.timeout` — Approval timeout duration
