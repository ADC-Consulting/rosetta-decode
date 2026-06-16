# Same root config for every environment. Variables are declared here (no
# defaults); values are supplied by tfvars:
#   • env/common.tfvars  — shared across all envs
#   • env/<env>.tfvars   — per-env (environment, subscription_id)

# ── Per-environment (env/<env>.tfvars) ────────────────────────────────────────

variable "environment" {
  type        = string
  description = "Environment short name (dev | prd)."
}

variable "subscription_id" {
  type        = string
  description = "Azure subscription ID to deploy into."
}

# ── Shared (env/common.tfvars) ────────────────────────────────────────────────

variable "storage_replication_type" {
  type        = string
  description = "Storage replication type (LRS, ZRS, GRS, ...)."
}

variable "vnet_address_space" {
  type        = list(string)
  description = "VNet address space. Subnet /24s are derived from this base."
}

variable "openai_capacity" {
  type        = number
  description = "Model deployment capacity (TPM units)."
}

variable "openai_sku_name" {
  type        = string
  description = "Deployment SKU. DataZoneStandard keeps inference within the EU (GDPR / EU AI Act)."
}

variable "location" {
  type        = string
  description = "Azure region. Keep in the EU for GDPR data residency."
}

variable "project" {
  type        = string
  description = "Project tag value."
}

variable "ai_foundry_name" {
  type        = string
  description = "Base name for AI Foundry resources."
}

variable "openai_model_name" {
  type        = string
  description = "Azure OpenAI model/deployment name."
}

variable "openai_model_format" {
  type        = string
  description = "Model format."
}

variable "openai_model_version" {
  type        = string
  description = "Model version."
}

# ── Deployment #2 (optional) — Claude, gated by deploy_claude ─────────────────

variable "deploy_claude" {
  type        = bool
  description = "Deploy the second (Claude) model deployment."
}

variable "claude_model_name" {
  type        = string
  description = "Claude deployment model/deployment name."
}

variable "claude_model_format" {
  type        = string
  description = "Claude deployment model format."
}

variable "claude_model_version" {
  type        = string
  description = "Claude deployment model version."
}

variable "claude_sku_name" {
  type        = string
  description = "Claude deployment SKU."
}

variable "claude_capacity" {
  type        = number
  description = "Claude deployment capacity (TPM units)."
}
