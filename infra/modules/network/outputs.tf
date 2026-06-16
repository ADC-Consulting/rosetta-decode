output "vnet_id" {
  value       = azurerm_virtual_network.main.id
  description = "Virtual network resource ID."
}

output "subnet_private_endpoint_id" {
  value       = azurerm_subnet.private_endpoint.id
  description = "Private-endpoint subnet ID (hosts the AI Foundry PE)."
}
