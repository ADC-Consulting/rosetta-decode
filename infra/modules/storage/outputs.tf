output "storage_account_id" {
  value       = azurerm_storage_account.main.id
  description = "Storage account resource ID (input to the AI Foundry hub)."
}
