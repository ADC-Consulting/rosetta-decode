#!/usr/bin/env bash
# Bootstrap (or tear down) the Terraform remote-state backend.
#
# Solves the chicken-and-egg: the azurerm backend needs a storage account +
# container to exist BEFORE `terraform init`. This is a one-time, out-of-band
# step managed with the Azure CLI, not Terraform.
#
# Usage:
#   ./bootstrap-backend.sh create     # create RG + storage account + container
#   ./bootstrap-backend.sh destroy    # delete the state RG (DESTROYS ALL STATE)
#
# The storage account name is DERIVED from the project + a short hash of the
# subscription, so it's globally unique without manual fiddling. `create` writes
# the resolved names to infra/backend.hcl (gitignored), which terraform init reads.
#
# Override any default via env vars:
#   TF_STATE_RG, TF_STATE_SA, TF_STATE_CONTAINER, TF_STATE_LOCATION, TF_STATE_PROJECT
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_HCL="$SCRIPT_DIR/../backend.hcl"

PROJECT="${TF_STATE_PROJECT:-rosetta-decode}"
PROJECT_COMPACT="$(printf '%s' "$PROJECT" | tr -d '-' | tr '[:upper:]' '[:lower:]')"
SUB_HASH="$(printf '%s' "$(az account show --query id -o tsv)" | shasum | cut -c1-6)"

STATE_RG="${TF_STATE_RG:-rg-${PROJECT}-tfstate}"
# tfs + project + 6-char sub hash → e.g. tfsrosettadecode1a2b3c (<=24, globally unique)
STATE_SA="${TF_STATE_SA:-tfs${PROJECT_COMPACT}${SUB_HASH}}"
STATE_CONTAINER="${TF_STATE_CONTAINER:-tfstate}"
LOCATION="${TF_STATE_LOCATION:-westeurope}"        # EU region (GDPR / EU AI Act)

action="${1:-}"

create() {
  # Idempotent: if the account already exists in this subscription, reuse it
  # (and whatever RG it lives in) instead of failing.
  existing_rg="$(az storage account show --name "$STATE_SA" --query resourceGroup -o tsv 2>/dev/null || true)"
  if [[ -n "$existing_rg" ]]; then
    STATE_RG="$existing_rg"
    echo "→ Storage account $STATE_SA already exists in RG '$STATE_RG' — reusing."
  else
    if [[ "$(az storage account check-name --name "$STATE_SA" --query nameAvailable -o tsv)" != "true" ]]; then
      echo "!! '$STATE_SA' is taken in another tenant. Set TF_STATE_SA to override." >&2
      exit 1
    fi
    echo "→ Resource group: $STATE_RG ($LOCATION)"
    az group create --name "$STATE_RG" --location "$LOCATION" --output none

    echo "→ Storage account: $STATE_SA"
    az storage account create \
      --name "$STATE_SA" \
      --resource-group "$STATE_RG" \
      --location "$LOCATION" \
      --sku Standard_LRS \
      --kind StorageV2 \
      --min-tls-version TLS1_2 \
      --https-only true \
      --allow-blob-public-access false \
      --output none
  fi

  # Versioning + soft-delete: lets you recover a clobbered/corrupted state file.
  echo "→ Enabling blob versioning + soft-delete"
  az storage account blob-service-properties update \
    --account-name "$STATE_SA" \
    --resource-group "$STATE_RG" \
    --enable-versioning true \
    --enable-delete-retention true \
    --delete-retention-days 7 \
    --output none

  echo "→ Container: $STATE_CONTAINER"
  key="$(az storage account keys list --account-name "$STATE_SA" --resource-group "$STATE_RG" --query '[0].value' -o tsv)"
  az storage container create \
    --name "$STATE_CONTAINER" \
    --account-name "$STATE_SA" \
    --account-key "$key" \
    --output none

  # Write the resolved backend coordinates for terraform init to read.
  cat > "$BACKEND_HCL" <<EOF
resource_group_name  = "$STATE_RG"
storage_account_name = "$STATE_SA"
container_name       = "$STATE_CONTAINER"
EOF

  cat <<EOF

✓ Backend ready. Wrote infra/backend.hcl:
    resource_group_name  = "$STATE_RG"
    storage_account_name = "$STATE_SA"
    container_name       = "$STATE_CONTAINER"

Next: make tf-init ENV=dev
EOF
}

destroy() {
  echo "!! This deletes resource group '$STATE_RG' and ALL Terraform state in it."
  echo "!! Destroy the environments FIRST (make tf-destroy ENV=...) or you will"
  echo "!! orphan their resources with no state to manage them."
  read -r -p "Type the resource group name to confirm: " confirm
  if [[ "$confirm" != "$STATE_RG" ]]; then
    echo "Aborted."; exit 1
  fi
  az group delete --name "$STATE_RG" --yes
  rm -f "$BACKEND_HCL"
  echo "✓ Backend removed."
}

case "$action" in
  create)  create ;;
  destroy) destroy ;;
  *) echo "Usage: $0 create|destroy" >&2; exit 2 ;;
esac
