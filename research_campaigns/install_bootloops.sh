#!/usr/bin/env bash
# Reproduce the tested Python toolkit installation; external engines are optional.
set -euo pipefail
toolkit_dir="${1:?Usage: install_bootloops.sh ABSOLUTE_CHECKOUT_PATH}"
case "$toolkit_dir" in /*) ;; *) echo "Use an absolute checkout path" >&2; exit 2 ;; esac
upstream_commit=66b680ce742e654cfe86da4f072a69061fe182b1
if [ ! -d "$toolkit_dir" ]; then
  git clone https://github.com/BootLoops-ai/bootloops.git "$toolkit_dir"
fi
test "$(git -C "$toolkit_dir" remote get-url origin)" = "https://github.com/BootLoops-ai/bootloops.git"
test -z "$(git -C "$toolkit_dir" status --porcelain --untracked-files=no)"
git -C "$toolkit_dir" checkout --detach "$upstream_commit"
python3 -m venv "$toolkit_dir/.venv"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
"$toolkit_dir/.venv/bin/python" -m pip install -r "$script_dir/bootloops_requirements.lock"
# Plain source packages: expose the documented tools root to this venv.
"$toolkit_dir/.venv/bin/python" - "$toolkit_dir" <<'PY'
import pathlib, site, sys
root=pathlib.Path(sys.argv[1]).resolve()
pathlib.Path(site.getsitepackages()[0], "bootloops.pth").write_text(str(root/"tools")+"\n")
PY
cd "$toolkit_dir"
export PATH="$toolkit_dir/.venv/bin:$PATH"
python run_selftests.py --par 4 --timeout 300
