# NVIDIA GPU Operator CRD Field Reference

Full CRD schemas are in `openshift/crds/gpu-operator-certified/`.

## ClusterPolicy (nvidia.com/v1)

Master CR that configures the entire GPU stack on the cluster.

### spec.operator
- `defaultRuntime` — Container runtime: `crio` (OpenShift default), `containerd`, `docker`
- `runtimeClass` — RuntimeClass name: `nvidia`
- `initContainer` — Init container config (usually `{}`)
- `use_ocp_driver_toolkit` — Use OpenShift Driver Toolkit for driver builds (default: true)

### spec.driver
- `enabled` — Install GPU driver (false if using pre-installed/in-tree driver)
- `useNvidiaDriverCRD` — Use NVIDIADriver CR for per-node-group config
- `kernelModuleType` — `auto`, `open`, `proprietary` (kernel module type)
- `upgradePolicy.autoUpgrade` — Auto-upgrade driver on operator update
- `upgradePolicy.maxParallelUpgrades` — Max nodes upgrading simultaneously
- `upgradePolicy.maxUnavailable` — Max unavailable nodes during upgrade (number or %)
- `upgradePolicy.drain.enable` — Drain node before driver upgrade
- `upgradePolicy.drain.force` — Force drain (evict pods with no controller)
- `upgradePolicy.drain.deleteEmptyDir` — Delete emptyDir volumes during drain
- `upgradePolicy.drain.timeoutSeconds` — Drain timeout
- `upgradePolicy.podDeletion` — Pod deletion settings during upgrade
- `upgradePolicy.waitForCompletion.timeoutSeconds` — Wait for upgrade completion
- `licensingConfig.nlsEnabled` — NVIDIA License System for vGPU
- `licensingConfig.configMapName` — ConfigMap with license server info
- `certConfig.name` — ConfigMap with custom CA certs
- `kernelModuleConfig.name` — ConfigMap with kernel module parameters
- `repoConfig.configMapName` — ConfigMap with custom package repos
- `virtualTopology.config` — vGPU topology config

### spec.dcgm
- `enabled` — Deploy DCGM (Data Center GPU Manager) for GPU health monitoring

### spec.dcgmExporter
- `serviceMonitor.enabled` — Create ServiceMonitor for Prometheus scraping
- `config.name` — Custom metrics ConfigMap (default: all metrics)

### spec.devicePlugin
- `config.name` — Custom device plugin ConfigMap
- `config.default` — Default config profile name
- `mps.root` — MPS (Multi-Process Service) root path for GPU sharing

### spec.gfd
- GPU Feature Discovery — discovers GPU properties and creates node labels
- Usually `{}` (empty = defaults)

### spec.migManager
- `enabled` — Enable MIG (Multi-Instance GPU) manager
- `config.name` — ConfigMap with MIG partition profiles

### spec.mig
- `strategy` — `single` (one MIG profile per GPU) or `mixed` (multiple profiles)

### spec.toolkit
- `enabled` — Install NVIDIA Container Toolkit

### spec.validator
- `plugin.env` — Environment variables for the validator
- `plugin.env[].WITH_WORKLOAD=true` — Run a test workload to validate GPU

### spec.nodeStatusExporter
- `enabled` — Export node GPU status metrics

### spec.daemonsets
- `updateStrategy` — `RollingUpdate` or `OnDelete`
- `rollingUpdate.maxUnavailable` — Max unavailable during rolling update

### spec.sandboxWorkloads
- `enabled` — Enable sandbox (VM) GPU support
- `defaultWorkload` — `container`, `vm-passthrough`, `vm-vgpu`

### spec.vgpuManager
- `enabled` — Install vGPU manager for VM GPU sharing

### spec.vgpuDeviceManager
- `enabled` — Manage vGPU device lifecycle

### spec.sandboxDevicePlugin
- `enabled` — Device plugin for sandbox/VM workloads

### spec.vfioManager
- `enabled` — VFIO manager for GPU passthrough to VMs

### spec.gds
- `enabled` — GPUDirect Storage support

### spec.gdrcopy
- `enabled` — GPUDirect RDMA copy support

## NVIDIADriver (nvidia.com/v1alpha1)

Per-node-group driver configuration (used when `spec.driver.useNvidiaDriverCRD=true`).

**Key spec fields:**
- `spec.driverType` — `gpu` or `vgpu`
- `spec.repository` — Container image repository (e.g. `nvcr.io/nvidia`)
- `spec.image` — Driver image name (e.g. `driver`)
- `spec.version` — Driver version or digest
- `spec.nodeSelector` — Target specific node groups
- `spec.tolerations` — Tolerations for driver pods
- `spec.kernelModuleType` — `auto`, `open`, `proprietary`
- `spec.upgradePolicy` — Same structure as ClusterPolicy driver upgradePolicy
- `spec.licensingConfig` — Same structure as ClusterPolicy
- `spec.certConfig` — Custom CA certificates
- `spec.repoConfig` — Custom package repositories
- `spec.virtualTopology` — vGPU topology configuration

## Common GPU Labels (set by GPU Operator + NFD)

| Label | Source | Description |
|-------|--------|-------------|
| `nvidia.com/gpu.present` | GPU Operator | GPU detected on node |
| `nvidia.com/gpu.count` | GPU Operator | Number of GPUs |
| `nvidia.com/gpu.product` | GFD | GPU product name (e.g. NVIDIA-H100-SXM) |
| `nvidia.com/gpu.memory` | GFD | GPU memory in MB |
| `nvidia.com/gpu.family` | GFD | GPU architecture family |
| `nvidia.com/cuda.driver.major` | GFD | CUDA driver major version |
| `nvidia.com/cuda.runtime.major` | GFD | CUDA runtime major version |
| `nvidia.com/mig.strategy` | MIG Manager | MIG strategy (single/mixed) |
| `feature.node.kubernetes.io/pci-10de.present` | NFD | NVIDIA PCI device detected |
