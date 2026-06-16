output "ai_services_id" {
  value       = azurerm_cognitive_account.ai_services.id
  description = "AI Services (Cognitive) account resource ID."
}

output "ai_services_endpoint" {
  value       = azurerm_cognitive_account.ai_services.endpoint
  description = "AI Services endpoint URL."
}

output "ai_foundry_id" {
  value       = azurerm_ai_foundry.ai_foundry.id
  description = "AI Foundry hub resource ID."
}

output "ai_project_id" {
  value       = azurerm_ai_foundry_project.ai_project.id
  description = "AI Foundry project resource ID."
}

output "openai_deployment_name" {
  value       = azurerm_cognitive_deployment.openai_model.name
  description = "Name of the served Azure OpenAI deployment."
}

output "model_api_key" {
  value       = azurerm_cognitive_account.ai_services.primary_access_key
  description = "Primary API key for the AI Services account."
  sensitive   = true
}
