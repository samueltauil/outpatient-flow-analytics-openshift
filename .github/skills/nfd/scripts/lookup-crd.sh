#!/usr/bin/env bash
# Look up CRD field details from the full OpenAPI schema.
# Usage:
#   ./lookup-crd.sh                              # List available CRDs
#   ./lookup-crd.sh nodefeaturediscoveries              # Show top-level spec fields
#   ./lookup-crd.sh nodefeaturediscoveries spec.workerConfig  # Show nested field details
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../../.." 2>/dev/null || cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)" && pwd)"
CRD_DIR="$REPO_ROOT/openshift/crds/nfd"

if [ $# -eq 0 ]; then
  echo "Available CRDs:"
  for f in "$CRD_DIR"/*.yaml; do
    name=$(grep '^  name:' "$f" | head -1 | awk '{print $2}')
    kind=$(grep '    kind:' "$f" | head -1 | awk '{print $2}')
    echo "  $kind  →  $name"
  done
  echo ""
  echo "Usage: $0 <crd-keyword> [field.path]"
  exit 0
fi

KEYWORD="$1"
FIELD_PATH="${2:-spec}"

CRD_FILE=$(ls "$CRD_DIR"/*.yaml 2>/dev/null | grep -i "$KEYWORD" | head -1)
if [ -z "$CRD_FILE" ]; then
  echo "No CRD matching '$KEYWORD'. Available files:"
  ls "$CRD_DIR"/*.yaml | xargs -I{} basename {}
  exit 1
fi

echo "# CRD: $(basename "$CRD_FILE")"
echo "# Field path: $FIELD_PATH"
echo ""

if command -v python3 &>/dev/null && python3 -c "import yaml" 2>/dev/null; then
  CRD_FILE_PATH="$CRD_FILE" FIELD="$FIELD_PATH" python3 << 'PYEOF'
import yaml, os

with open(os.environ['CRD_FILE_PATH']) as f:
    doc = yaml.safe_load(f)

versions = doc.get('spec', {}).get('versions', [{}])
schema = versions[0].get('schema', {}).get('openAPIV3Schema', {})
field_path = os.environ['FIELD']

path_parts = field_path.split('.')
node = schema
breadcrumb = []
for part in path_parts:
    breadcrumb.append(part)
    props = node.get('properties', {})
    if part in props:
        node = props[part]
    else:
        print(f"Field '{'.'.join(breadcrumb)}' not found.")
        if props:
            print(f"Available at '{'.'.join(breadcrumb[:-1])}': {', '.join(sorted(props.keys()))}")
        raise SystemExit(0)

desc = node.get('description', '')
ntype = node.get('type', node.get('$ref', 'object'))
print(f'Type: {ntype}')
if desc:
    print(f'Description: {desc}')
if 'enum' in node:
    print(f"Enum: {node['enum']}")
if 'default' in node:
    print(f"Default: {node['default']}")

props = node.get('properties', {})
if props:
    print()
    print(f'Child fields ({len(props)}):')
    for name in sorted(props.keys()):
        child = props[name]
        ct = child.get('type', 'object')
        cd = child.get('description', '')
        if cd:
            cd = cd.split('\n')[0][:100]
        print(f'  .{name} ({ct}): {cd}')

items = node.get('items', {})
if items and items.get('properties'):
    aprops = items['properties']
    print()
    print(f'Array item fields ({len(aprops)}):')
    for name in sorted(aprops.keys()):
        child = aprops[name]
        ct = child.get('type', 'object')
        cd = child.get('description', '')
        if cd:
            cd = cd.split('\n')[0][:100]
        print(f'  .{name} ({ct}): {cd}')
PYEOF
else
  # Fallback: extract the YAML block under the last path segment
  LAST_FIELD="${FIELD_PATH##*.}"
  echo "(python3+PyYAML not available — showing grep context for '$LAST_FIELD')"
  echo ""
  grep -n -A 40 "^ *${LAST_FIELD}:" "$CRD_FILE" | head -50
fi
