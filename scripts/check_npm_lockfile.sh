#!/usr/bin/env bash
# Fail if package-lock.json is out of sync with package.json
staged=$(git diff --cached --name-only)
if echo "$staged" | grep -q "src/frontend/package\.json"; then
    if [ -n "$(git diff src/frontend/package-lock.json)" ] || \
       git ls-files --others --exclude-standard src/frontend/package-lock.json | grep -q .; then
        echo "ERROR: package-lock.json is out of sync with package.json"
        echo "Run 'npm install' in src/frontend/ then stage package-lock.json"
        exit 1
    fi
fi
