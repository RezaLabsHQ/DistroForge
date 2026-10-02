#!/usr/bin/env bash
# Runs INSIDE a fresh distro container as root. Prepares a normal sudo user,
# installs DistroForge from /src, then exercises it for real.
set -euo pipefail

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

say "Bootstrapping $(. /etc/os-release; echo "$PRETTY_NAME")"
if command -v apt-get >/dev/null; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq && apt-get install -y -qq python3 python3-venv sudo >/dev/null
elif command -v dnf >/dev/null; then
    dnf install -y -q python3 sudo >/dev/null
elif command -v pacman >/dev/null; then
    pacman -Syu --noconfirm --needed python sudo >/dev/null
fi
useradd -m tester
echo 'tester ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/tester
cp -r /src /tmp/src && chown -R tester /tmp/src

sudo -u tester -H bash -euo pipefail <<'AS_USER'
say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
cd ~
python3 -m venv venv
venv/bin/pip install -q /tmp/src
export PATH="$HOME/venv/bin:$PATH"

say "doctor"
distroforge doctor

say "dry-run of every built-in profile"
for profile in $(distroforge profiles | awk '/^[a-z]/ {print $1}'); do
    distroforge apply --profile "$profile" --dry-run > "/tmp/plan-$profile.txt"
    echo "  $profile: $(grep -c '^ *[0-9]*\. ' "/tmp/plan-$profile.txt" || true) steps"
done

say "dry-run of the ENTIRE catalog"
distroforge apply $(distroforge list --ids) --dry-run > /tmp/plan-all.txt
tail -1 /tmp/plan-all.txt

say "real install: tree jq htop + zoxide shell init"
distroforge apply tree jq htop zoxide --yes
for bin in tree jq htop zoxide; do command -v "$bin" >/dev/null || { echo "MISSING: $bin"; exit 1; }; done
grep -q "distroforge:zoxide" ~/.bashrc || { echo "zoxide block missing from .bashrc"; exit 1; }

say "idempotency: second run must be a no-op"
out="$(distroforge apply tree jq htop zoxide --yes)"
echo "$out" | tail -3
echo "$out" | grep -q "Nothing to do" || { echo "NOT IDEMPOTENT"; exit 1; }
[ "$(grep -c 'distroforge:zoxide' ~/.bashrc)" = 2 ] || { echo "duplicate rc block"; exit 1; }

say "sysctl tweak (root file write via staged install)"
# Containers can't change live kernel parameters (/proc/sys is read-only), so the
# "sysctl -p" step may fail here; the persisted, root-owned drop-in must exist regardless.
distroforge apply inotify-watches --yes || echo "(sysctl apply failed as expected in a container)"
grep -q "fs.inotify.max_user_watches = 524288" /etc/sysctl.d/99-distroforge-fs-inotify-max-user-watches.conf
stat -c '%U %a' /etc/sysctl.d/99-distroforge-fs-inotify-max-user-watches.conf | grep -q "root 644"

say "user catalog extension"
mkdir -p ~/.config/distroforge/catalog.d
cat > ~/.config/distroforge/catalog.d/mine.yaml <<'YAML'
items:
  - id: my-tools
    name: My tools
    category: utilities
    install:
      - apt: [file]
      - dnf: [file]
      - pacman: [file]
YAML
distroforge validate ~/.config/distroforge/catalog.d/mine.yaml
distroforge apply my-tools --yes
command -v file >/dev/null

say "integrate (menu entry)"
distroforge integrate
test -f ~/.local/share/applications/distroforge.desktop

say "ALL CHECKS PASSED"
AS_USER
