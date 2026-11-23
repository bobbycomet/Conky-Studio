#!/usr/bin/env bash
# Refreshes every translation catalog (conkystudio/i18n/conkystudio_*.ts) from
# the source code. Run after changing UI text, before committing.
#
#   conkystudio/tools/update_translations.sh            # update existing catalogs
#   conkystudio/tools/update_translations.sh de pt_BR   # also start new ones
#
# Needs pylupdate6 (ships with PyQt6). The .ts files are the source of truth;
# .qm files are compiled from them by lrelease during the AppImage build.
set -euo pipefail

TOOLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$TOOLS_DIR/../.." && pwd)"
I18N_DIR="$REPO_ROOT/conkystudio/i18n"
cd "$REPO_ROOT"

command -v pylupdate6 >/dev/null 2>&1 || { echo "pylupdate6 not found (pip install PyQt6)"; exit 1; }

# New catalogs start from a minimal header (the language attribute matters for
# plural forms).
for lang in "$@"; do
    ts="$I18N_DIR/conkystudio_$lang.ts"
    if [[ ! -f "$ts" ]]; then
        echo "==> New catalog: ${ts#"$REPO_ROOT"/}"
        printf '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n<TS version="2.1" language="%s"></TS>\n' "$lang" > "$ts"
    fi
done

shopt -s nullglob
catalogs=("$I18N_DIR"/conkystudio_*.ts)
if [[ ${#catalogs[@]} -eq 0 ]]; then
    echo "No catalogs yet. Start one with: $0 <lang>   (e.g. $0 ru)"
    exit 0
fi

python3 "$TOOLS_DIR/i18n_node_strings.py"

ts_args=()
for ts in "${catalogs[@]}"; do ts_args+=(--ts "$ts"); done
pylupdate6 --no-obsolete --exclude tests --exclude tools conkystudio "${ts_args[@]}"
