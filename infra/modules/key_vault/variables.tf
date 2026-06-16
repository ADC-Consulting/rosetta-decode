variable "rg_name" {
  type        = string
  description = "Resource group name."
}

variable "rg_location" {
  type        = string
  description = "Resource group location."
}

variable "key_vault_name" {
  type        = string
  description = "Key Vault name (globally unique)."
}

variable "kv_soft_delete_retention_days" {
  type        = number
  description = "Key Vault soft-delete retention in days."
  default     = 7
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to all resources."
  default     = {}
}
