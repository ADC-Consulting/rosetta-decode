# Resource Group — owns all rosetta-decode Azure resources for the environment.
resource "azurerm_resource_group" "main" {
  name     = var.rg_name
  location = var.location
  tags     = var.tags
}
