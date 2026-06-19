variable "rg_name" {
  type        = string
  description = "Resource group name."
}

variable "rg_location" {
  type        = string
  description = "Resource group location."
}

variable "storage_account_name" {
  type        = string
  description = "Storage account name (3-24 chars, lowercase alphanumeric, globally unique)."
}

variable "storage_replication_type" {
  type        = string
  description = "Storage replication type (LRS, ZRS, GRS, ...)."
  default     = "LRS"
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to all resources."
  default     = {}
}
