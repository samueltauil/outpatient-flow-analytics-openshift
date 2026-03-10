# NFD CRD Field Reference

Full CRD schemas are in `openshift/crds/nfd/`.

## NodeFeatureDiscovery (nfd.openshift.io/v1)

Main operator CR that deploys NFD master and worker components.

**Key spec fields:**
- `spec.operand.image` — NFD container image
- `spec.operand.imagePullPolicy` — `Always`, `IfNotPresent`, `Never`
- `spec.operand.servicePort` — gRPC service port (default: 12000)
- `spec.topologyUpdater` — Enable topology-aware scheduling info (default: false)
- `spec.workerConfig.configData` — Worker configuration (YAML string), see below

### workerConfig.configData structure

```yaml
core:
  sleepInterval: 60s           # How often to re-scan features
  featureSources:              # List of feature sources to enable
    - pci
    - usb
    - cpu
    - memory
    - network
    - storage
    - system
    - kernel
    - local
sources:
  pci:
    deviceClassWhitelist:       # PCI device classes to detect
      - "0200"                  # Ethernet controller
      - "03"                    # Display controller (all GPUs)
      - "12"                    # Processing accelerators (compute GPUs)
      - "0280"                  # Network controller (other)
    deviceLabelFields:          # PCI fields to include in labels
      - "vendor"                # Creates: feature.node.kubernetes.io/pci-<vendor>.present
      - "device"                # Creates: feature.node.kubernetes.io/pci-<vendor>_<device>.present
      - "subsystem_vendor"
      - "subsystem_device"
      - "class"
  cpu:
    cpuid:
      attributeBlacklist: []    # CPUID flags to exclude
      attributeWhitelist: []    # CPUID flags to include (empty = all)
  usb:
    deviceClassWhitelist: []    # USB device classes to detect
    deviceLabelFields: []
  kernel:
    configOpts: []              # Kernel config options to detect
  custom: []                    # Custom feature definitions
```

## NodeFeatureRule (nfd.openshift.io/v1)

Custom rules for creating node labels based on detected features.

**Key spec fields:**
- `spec.rules` — List of label rules
- `spec.rules[].name` — Rule name (for debugging)
- `spec.rules[].labels` — Labels to apply when rule matches (key: value map)
- `spec.rules[].labelsTemplate` — Go template for dynamic label values
- `spec.rules[].annotations` — Annotations to apply
- `spec.rules[].taints` — Taints to apply
- `spec.rules[].extendedResources` — Extended resources to advertise
- `spec.rules[].matchFeatures` — Feature matchers (AND logic within a rule)
- `spec.rules[].matchAny` — Alternative matchers (OR logic)

### matchFeatures structure

```yaml
matchFeatures:
  - feature: pci.device          # Feature source.name
    matchExpressions:
      vendor: {op: In, value: ["10de"]}           # NVIDIA
      class: {op: In, value: ["0300", "0302"]}     # Display/3D controller
  - feature: cpu.cpuid
    matchExpressions:
      AVX512F: {op: Exists}
  - feature: kernel.version
    matchExpressions:
      major: {op: Gte, value: ["5"]}
```

**Operators:** `In`, `NotIn`, `Exists`, `DoesNotExist`, `Gt`, `Lt`, `Gte`, `Lte`, `IsTrue`, `IsFalse`

## NodeFeature (nfd.openshift.io/v1)

Per-node feature inventory, auto-created by NFD workers. Generally not user-managed.

**Key spec fields:**
- `spec.features` — Map of detected features per source
- `spec.labels` — Computed labels for this node

## Common NVIDIA PCI Device IDs

| GPU Model | Vendor | Device IDs |
|-----------|--------|------------|
| H100 SXM | 10de | 2330 |
| H100 PCIe | 10de | 2331 |
| A100 SXM | 10de | 20b0 |
| A100 PCIe | 10de | 20b2, 20f1 |
| L40 | 10de | 26b5 |
| T4 | 10de | 1eb8 |
| V100 SXM | 10de | 1db1 |
| V100 PCIe | 10de | 1db4 |

All NVIDIA GPUs use vendor ID `10de` and PCI class `03` (Display controller) or `12` (Processing accelerator).
