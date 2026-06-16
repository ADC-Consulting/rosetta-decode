# Shared across all environments. Loaded before env/<env>.tfvars, which only
# sets environment + subscription_id.
location = "westeurope"
project  = "rosetta-decode"

ai_foundry_name = "rosetta-decode"

storage_replication_type = "LRS"
vnet_address_space       = ["10.0.0.0/16"]

openai_model_name    = "gpt-5.4"
openai_model_format  = "OpenAI"
openai_model_version = "2026-03-05"
openai_capacity      = 900
openai_sku_name      = "DataZoneStandard"

# Deployment #2 (Claude) — flip deploy_claude to true once Anthropic models are
# enabled in the tenant, and set the real Azure model coords below.
deploy_claude        = false
claude_model_name    = "claude-opus-4-1"
claude_model_format  = "Anthropic"
claude_model_version = "1"
claude_sku_name      = "GlobalStandard"
claude_capacity      = 1
