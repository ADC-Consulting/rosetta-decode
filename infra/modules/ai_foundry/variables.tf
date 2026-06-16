variable "ai_foundry_name" {
  type        = string
  description = "Base name for AI Foundry resources (suffixes are added per resource/environment)."
}

variable "environment" {
  type        = string
  description = "Environment short name (dev | prd)."
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to all resources."
  default     = {}
}

variable "rg_name" {
  type        = string
  description = "Resource group name."
}

variable "rg_location" {
  type        = string
  description = "Resource group location."
}

# --- Dependencies from the foundation module ---

variable "storage_account_id" {
  type        = string
  description = "Storage account ID for the Foundry hub."
}

variable "key_vault_id" {
  type        = string
  description = "Key Vault ID for the Foundry hub and credential secrets."
}

variable "vnet_id" {
  type        = string
  description = "Virtual network ID for the private DNS zone link."
}

variable "subnet_ai_foundry_id" {
  type        = string
  description = "Subnet ID for the AI Foundry private endpoint."
}

# --- Model deployment ---

variable "openai_model_name" {
  type        = string
  description = "Azure OpenAI model/deployment name (OpenAI-compatible route)."
}

variable "openai_model_format" {
  type        = string
  description = "Model format."
  default     = "OpenAI"
}

variable "openai_model_version" {
  type        = string
  description = "Model version."
}

variable "openai_capacity" {
  type        = number
  description = "Deployment capacity (TPM units)."
}

variable "openai_sku_name" {
  type        = string
  description = "Deployment SKU. DataZoneStandard keeps inference within the geography (EU); GlobalStandard may route globally."
  default     = "DataZoneStandard"
}

# --- Deployment #2 (optional) — Claude, gated by deploy_claude ---

variable "deploy_claude" {
  type        = bool
  description = "Deploy the second (Claude) model deployment."
  default     = false
}

variable "claude_model_name" {
  type        = string
  description = "Claude deployment model/deployment name."
  default     = "claude-opus-4-1"
}

variable "claude_model_format" {
  type        = string
  description = "Claude deployment model format."
  default     = "Anthropic"
}

variable "claude_model_version" {
  type        = string
  description = "Claude deployment model version."
  default     = "1"
}

variable "claude_sku_name" {
  type        = string
  description = "Claude deployment SKU."
  default     = "GlobalStandard"
}

variable "claude_capacity" {
  type        = number
  description = "Claude deployment capacity (TPM units)."
  default     = 1
}
