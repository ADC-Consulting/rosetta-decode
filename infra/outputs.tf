output "environment" {
  value       = var.environment
  description = "Active environment."
}

output "resource_group_name" {
  value       = module.resource_group.name
  description = "Resource group name."
}

output "ai_services_endpoint" {
  value       = module.ai_foundry.ai_services_endpoint
  description = "AI Services endpoint URL."
}

output "openai_deployment_name" {
  value       = module.ai_foundry.openai_deployment_name
  description = "Served Azure OpenAI deployment name."
}

output "key_vault_id" {
  value       = module.key_vault.key_vault_id
  description = "Key Vault holding the model credentials."
}
