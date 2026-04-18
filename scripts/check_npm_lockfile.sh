#!/usr/bin/env bash
# Fail if package.json is staged without package-lock.json
staged=$(git diff --cached --name-only)
if echo "$staged" | grep -q "src/frontend/package\.json"; then
    if ! echo "$staged" | grep -q "src/frontend/package-lock\.json"; then
        echo "ERROR: package.json staged without package-lock.json"
        echo "Run 'npm install' in src/frontend/ then stage package-lock.json"
        exit 1
    fi
fi
