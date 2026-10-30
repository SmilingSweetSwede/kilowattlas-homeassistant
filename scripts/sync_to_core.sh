#!/usr/bin/env bash
# Copy the integration into a home-assistant/core checkout as
# homeassistant/components/kilowattlas, stripping what only HACS needs.
#
#   scripts/sync_to_core.sh ~/src/home-assistant-core
set -euo pipefail
CORE="${1:?path to a home-assistant/core checkout}"
SRC="$(cd "$(dirname "$0")/.." && pwd)/custom_components/kilowattlas"
DST="$CORE/homeassistant/components/kilowattlas"
TESTS_DST="$CORE/tests/components/kilowattlas"

rm -rf "$DST" "$TESTS_DST"
mkdir -p "$DST" "$TESTS_DST"
rsync -a --exclude __pycache__ --exclude translations --exclude brand \
  --exclude frontend --exclude panel.py "$SRC/" "$DST/"
# The status page is HACS only: core integrations do not ship frontend code.
sed -i '/# hacs-only/d' "$DST/__init__.py"
# Core forbids `version`, uses its own issue tracker and docs site.
python3 - "$DST/manifest.json" <<'PY'
import json, sys
p = sys.argv[1]
m = json.load(open(p))
m.pop("version", None)
m.pop("issue_tracker", None)
m.pop("after_dependencies", None)
m["documentation"] = "https://www.home-assistant.io/integrations/kilowattlas"
json.dump(m, open(p, "w"), indent=2)
open(p, "a").write("\n")
PY
rsync -a --exclude __pycache__ --exclude test_panel.py "$(dirname "$SRC")/../tests/" "$TESTS_DST/"
# Tests import the custom_components path; core uses homeassistant.components.
sed -i 's/from custom_components\.kilowattlas/from homeassistant.components.kilowattlas/g; s/"custom_components\.kilowattlas/"homeassistant.components.kilowattlas/g; s/from pytest_homeassistant_custom_component\.components\./from tests.components./g; s/from pytest_homeassistant_custom_component\.common/from tests.common/g' "$TESTS_DST"/*.py
echo "synced to $DST and $TESTS_DST"
echo "next: cd $CORE && python -m script.hassfest && pytest tests/components/kilowattlas"
