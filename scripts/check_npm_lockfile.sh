#!/usr/bin/env bash
# Fail if package.json and package-lock.json are out of sync.
# Runs on every commit regardless of which files are staged.
cd "$(git rev-parse --show-toplevel)/src/frontend" || exit 1
if ! npm ci --dry-run 2>&1; then
    echo ""
    echo "ERROR: package-lock.json is out of sync with package.json"
    echo "Run 'npm install' in src/frontend/ then stage package-lock.json"
    exit 1
fi
