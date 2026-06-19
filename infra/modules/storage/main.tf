# Storage — the storage account backing the AI Foundry hub.

resource "azurerm_storage_account" "main" {
  name                            = var.storage_account_name
  resource_group_name             = var.rg_name
  location                        = var.rg_location
  account_tier                    = "Standard"
  account_replication_type        = var.storage_replication_type
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false

  tags = var.tags
}
