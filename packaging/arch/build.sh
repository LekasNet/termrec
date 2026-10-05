#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
version=$(sed -n 's/^version = "\([^"]*\)"$/\1/p' "$repo_root/pyproject.toml" | head -n 1)
if [ -z "$version" ]; then
  echo 'Cannot read project version' >&2
  exit 1
fi

cd "$repo_root/packaging/arch"
tar --exclude='__pycache__' --exclude='*.pyc' \
  --transform="s,^,termrec-$version/," \
  -czf "termrec-$version.tar.gz" \
  -C "$repo_root" pyproject.toml README.md LICENSE termrec packaging/bin
makepkg --clean --force
