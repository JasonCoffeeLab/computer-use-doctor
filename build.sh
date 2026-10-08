#!/bin/bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")" && pwd)"
output_dir="$project_dir/dist"
app_dir="$output_dir/Computer Use Doctor V9 Preview.app"
mkdir -p "$app_dir/Contents/MacOS" "$app_dir/Contents/Resources" "$project_dir/.build-cache"
xcrun swiftc -parse-as-library -O -target arm64-apple-macos14.0 \
  -module-cache-path "$project_dir/.build-cache" \
  "$project_dir/Sources/main.swift" -o "$app_dir/Contents/MacOS/ComputerUseDoctor"
cp "$project_dir/Resources/backend.py" "$project_dir/Resources/repair_core.py" "$project_dir/Resources/runtime_client.py" "$app_dir/Contents/Resources/"
cp "$project_dir/Resources/install_paths.py" "$app_dir/Contents/Resources/"
rsync -a --delete --exclude='.DS_Store' --exclude='__pycache__' --exclude='*.pyc' "$project_dir/Resources/vendor/" "$app_dir/Contents/Resources/vendor/"
cp "$project_dir/Resources/Info.plist" "$app_dir/Contents/Info.plist"
cp "$project_dir/LICENSE" "$app_dir/Contents/Resources/LICENSE.txt"
cp "$project_dir/docs/THIRD-PARTY-NOTICES.md" "$app_dir/Contents/Resources/THIRD-PARTY-NOTICES.md"
codesign --force --sign - "$app_dir"
codesign --verify --deep --strict "$app_dir"
