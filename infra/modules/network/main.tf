# Network — VNet + the private-endpoint subnet for the AI Foundry hub.
#
# Only what the config actually uses today. When a compute host is chosen
# (ACI / Container Apps / AKS / App Service), add its subnet then — delegated
# subnets are exclusive to their service and can't host a private endpoint,
# so each gets its own.
#
# Subnet /24s are derived from the VNet base (var.vnet_address_space) so dev and
# prd never overlap.

resource "azurerm_virtual_network" "main" {
  name                = "vnet-${var.environment}"
  location            = var.rg_location
  resource_group_name = var.rg_name
  address_space       = var.vnet_address_space
  tags                = var.tags
}

# Subnet: Private endpoints (NOT delegated) — hosts the AI Foundry PE.
resource "azurerm_subnet" "private_endpoint" {
  name                 = "subnet-pe-${var.environment}"
  resource_group_name  = var.rg_name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [cidrsubnet(var.vnet_address_space[0], 8, 1)]
  service_endpoints    = ["Microsoft.CognitiveServices"]
}
