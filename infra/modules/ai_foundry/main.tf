# AI Foundry — LLM inference for rosetta-decode. Replaces the borrowed deployment:
# owns its own AI Services account, Foundry hub + project, model deployments,
# private endpoint, and Key Vault secrets.

# AI Services (prerequisite for Foundry) - AIServices kind provides full Foundry capabilities
resource "azurerm_cognitive_account" "ai_services" {
  name                = "${var.ai_foundry_name}-services-${var.environment}"
  resource_group_name = var.rg_name
  location            = var.rg_location
  kind                = "AIServices"
  sku_name            = "S0"

  identity {
    type = "SystemAssigned"
  }

  # Required for stateful development in Foundry including agent service
  custom_subdomain_name      = "${var.ai_foundry_name}-${var.environment}"
  project_management_enabled = true

  tags = var.tags
}

# AI Foundry Hub
resource "azurerm_ai_foundry" "ai_foundry" {
  name                = "${var.ai_foundry_name}-hub-${var.environment}"
  location            = var.rg_location
  resource_group_name = var.rg_name
  storage_account_id  = var.storage_account_id
  key_vault_id        = var.key_vault_id

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags

  depends_on = [azurerm_cognitive_account.ai_services]
}

# AI Foundry Project (contains the served model)
resource "azurerm_ai_foundry_project" "ai_project" {
  name               = "${var.ai_foundry_name}-project-${var.environment}"
  location           = azurerm_ai_foundry.ai_foundry.location
  ai_services_hub_id = azurerm_ai_foundry.ai_foundry.id

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}

# Deployment #1 (primary) — the Azure OpenAI model (gpt-5.4), always deployed.
resource "azurerm_cognitive_deployment" "openai_model" {
  depends_on = [azurerm_ai_foundry_project.ai_project]

  name                 = var.openai_model_name
  cognitive_account_id = azurerm_cognitive_account.ai_services.id

  sku {
    name     = var.openai_sku_name
    capacity = var.openai_capacity
  }

  model {
    format  = var.openai_model_format
    name    = var.openai_model_name
    version = var.openai_model_version
  }
}

# # Deployment #2 (optional) — Claude. Gated by deploy_claude; configure via the
# # claude_* vars. Leave off until Anthropic models are enabled in the tenant.
# resource "azurerm_cognitive_deployment" "claude_model" {
#   depends_on = [azurerm_ai_foundry_project.ai_project]

#   count                = var.deploy_claude ? 1 : 0
#   name                 = var.claude_model_name
#   cognitive_account_id = azurerm_cognitive_account.ai_services.id

#   sku {
#     name     = var.claude_sku_name
#     capacity = var.claude_capacity
#   }

#   model {
#     format  = var.claude_model_format
#     name    = var.claude_model_name
#     version = var.claude_model_version
#   }
# }

# Wait for the Cognitive Account to be fully provisioned
resource "time_sleep" "wait_for_cognitive_account" {
  depends_on = [azurerm_cognitive_account.ai_services]

  create_duration = "60s"
}

# PRIVATE DNS ZONE FOR AI FOUNDRY
resource "azurerm_private_dns_zone" "ai_dns" {
  name                = "privatelink.openai.azure.com"
  resource_group_name = var.rg_name

  tags = var.tags
}

# PRIVATE ENDPOINT FOR AI FOUNDRY
resource "azurerm_private_endpoint" "ai_endpoint" {
  name                = "ai-private-endpoint-${var.environment}"
  resource_group_name = var.rg_name
  location            = var.rg_location
  subnet_id           = var.subnet_ai_foundry_id

  private_service_connection {
    name                           = "ai-privatesc-${var.environment}"
    private_connection_resource_id = azurerm_cognitive_account.ai_services.id
    is_manual_connection           = false
    subresource_names              = ["account"]
  }

  private_dns_zone_group {
    name                 = "ai-dns-zone-group-${var.environment}"
    private_dns_zone_ids = [azurerm_private_dns_zone.ai_dns.id]
  }

  depends_on = [time_sleep.wait_for_cognitive_account]

  tags = var.tags
}

# DNS ZONE LINK TO THE VNET
resource "azurerm_private_dns_zone_virtual_network_link" "ai_dns_link" {
  name                  = "ai-dns-link-${var.environment}"
  resource_group_name   = var.rg_name
  private_dns_zone_name = azurerm_private_dns_zone.ai_dns.name
  virtual_network_id    = var.vnet_id
  registration_enabled  = false

  tags = var.tags
}

# Store the API KEY in Key Vault (the endpoint is just a URL — exposed as an
# output instead, see outputs.tf: ai_services_endpoint).
resource "azurerm_key_vault_secret" "model_api_key" {
  name         = "model-api-key"
  value        = azurerm_cognitive_account.ai_services.primary_access_key
  key_vault_id = var.key_vault_id

  tags = var.tags
}
