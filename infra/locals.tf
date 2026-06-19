# Resource names follow a convention derived from project + environment, so the
# tfvars only carry `environment` (not the full names). Each name can still be
# overridden via its *_name_override variable when convention won't do (a name
# is already taken, or a legacy resource must be adopted).

locals {
  # Tags applied to every resource — defined once, passed into each module.
  tags = {
    environment = var.environment
    project     = var.project
  }

  # rosetta-decode-dev  →  used by hyphen-friendly names (RG, Key Vault).
  name_base = "${var.project}-${var.environment}"

  # rosettadecodedev  →  storage accounts forbid hyphens.
  name_compact = "${replace(var.project, "-", "")}${var.environment}"

  # Short deterministic suffix to keep the globally-unique storage name from
  # colliding with other tenants. Stable per (subscription, project).
  uniq = substr(md5("${var.subscription_id}-${var.project}"), 0, 4)

  rg_name              = local.name_base
  key_vault_name       = "kv-${local.name_base}"
  storage_account_name = "st${local.name_compact}${local.uniq}"
}

# Tripwire: storage account names are capped at 24 chars. Fail in plan/validate
# with a clear message rather than a confusing Azure API error at apply.
check "storage_account_name_length" {
  assert {
    condition     = length(local.storage_account_name) <= 24
    error_message = "Derived storage account name '${local.storage_account_name}' is ${length(local.storage_account_name)} chars (max 24). Shorten 'project'."
  }
}
