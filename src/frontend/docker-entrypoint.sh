#!/bin/sh
# Conditionally enables HTTP Basic Auth for the demo deployment, then starts
# nginx. Gated on DEMO_AUTH_USER/DEMO_AUTH_PASSWORD both being set and
# non-empty (Dokploy's Environment tab for the deployed demo). When either is
# unset — the case for local `make dev` / local `docker compose up`, which
# never set these — auth stays completely inert: nginx serves exactly as it
# does without this script.
set -eu

AUTH_DIR="/etc/nginx/conf.d/auth-enabled"
AUTH_CONF="$AUTH_DIR/auth.conf"
HTPASSWD_FILE="/etc/nginx/.htpasswd"

# Always start from "auth off": remove any leftover auth config/htpasswd
# first. Defensive against a container restart on a non-fresh filesystem
# with credentials since removed — this app's image is rebuilt fresh per
# deploy today, but don't assume that stays true.
rm -f "$AUTH_CONF" "$HTPASSWD_FILE"

if [ -n "${DEMO_AUTH_USER:-}" ] && [ -n "${DEMO_AUTH_PASSWORD:-}" ]; then
    mkdir -p "$AUTH_DIR"
    htpasswd -bc "$HTPASSWD_FILE" "$DEMO_AUTH_USER" "$DEMO_AUTH_PASSWORD"
    cat > "$AUTH_CONF" <<EOF
auth_basic "Rosetta demo access";
auth_basic_user_file $HTPASSWD_FILE;
EOF
fi

exec nginx -g "daemon off;"
