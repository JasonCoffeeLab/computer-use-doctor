#!/bin/bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$project_dir"
bash build.sh
ditto --norsrc -c -k --keepParent "dist/Computer Use Doctor V9 Preview.app" "dist/Computer-Use-Doctor-V9-Preview-arm64.zip"
COPYFILE_DISABLE=1 tar --exclude='.DS_Store' --exclude='__pycache__' --exclude='*.pyc' -czf dist/Computer-Use-Doctor-V9-Preview-source.tar.gz \
  Sources Resources tests docs .github .gitignore README.md LICENSE build.sh package.sh
cd dist
shasum -a 256 Computer-Use-Doctor-V9-Preview-arm64.zip Computer-Use-Doctor-V9-Preview-source.tar.gz > SHA256SUMS
