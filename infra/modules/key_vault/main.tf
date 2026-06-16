# Key Vault — holds the AI Foundry hub config and the model credential secrets.

data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "main" {
  name                = var.key_vault_name
  location            = var.rg_location
  resource_group_name = var.rg_name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  # Access-policy mode (not RBAC): setting a policy is a management-plane action
  # a Contributor can perform, so the deployer can self-grant secret access
  # without needing User Access Administrator.
  #
  # TODO: switch back to RBAC (rbac_authorization_enabled = true + remove the
  # access_policy block) once an admin can assign "Key Vault Secrets Officer" to
  # the deploy principal. RBAC is Microsoft's recommended model; access policies
  # are the fallback while we're Contributor-only.
  rbac_authorization_enabled = false

  purge_protection_enabled   = true
  soft_delete_retention_days = var.kv_soft_delete_retention_days

  # Grant the deploying principal data-plane access to write the model secret.
  access_policy {
    tenant_id          = data.azurerm_client_config.current.tenant_id
    object_id          = data.azurerm_client_config.current.object_id
    secret_permissions = ["Get", "List", "Set", "Delete", "Purge", "Recover"]
  }

  tags = var.tags
}
