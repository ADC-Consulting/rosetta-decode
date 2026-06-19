module "resource_group" {
  source   = "./modules/resource_group"
  rg_name  = local.rg_name
  location = var.location
  tags     = local.tags
}

module "network" {
  source             = "./modules/network"
  rg_name            = module.resource_group.name
  rg_location        = module.resource_group.location
  environment        = var.environment
  vnet_address_space = var.vnet_address_space
  tags               = local.tags
}

module "storage" {
  source                   = "./modules/storage"
  rg_name                  = module.resource_group.name
  rg_location              = module.resource_group.location
  storage_account_name     = local.storage_account_name
  storage_replication_type = var.storage_replication_type
  tags                     = local.tags
}

module "key_vault" {
  source         = "./modules/key_vault"
  rg_name        = module.resource_group.name
  rg_location    = module.resource_group.location
  key_vault_name = local.key_vault_name
  tags           = local.tags
}

module "ai_foundry" {
  source               = "./modules/ai_foundry"
  ai_foundry_name      = var.ai_foundry_name
  environment          = var.environment
  rg_name              = module.resource_group.name
  rg_location          = module.resource_group.location
  storage_account_id   = module.storage.storage_account_id
  key_vault_id         = module.key_vault.key_vault_id
  vnet_id              = module.network.vnet_id
  subnet_ai_foundry_id = module.network.subnet_private_endpoint_id
  openai_model_name    = var.openai_model_name
  openai_model_format  = var.openai_model_format
  openai_model_version = var.openai_model_version
  openai_capacity      = var.openai_capacity
  openai_sku_name      = var.openai_sku_name
  deploy_claude        = var.deploy_claude
  claude_model_name    = var.claude_model_name
  claude_model_format  = var.claude_model_format
  claude_model_version = var.claude_model_version
  claude_sku_name      = var.claude_sku_name
  claude_capacity      = var.claude_capacity
  tags                 = local.tags
}
