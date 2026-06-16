variable "rg_name" {
  type        = string
  description = "Resource group name."
}

variable "rg_location" {
  type        = string
  description = "Resource group location."
}

variable "environment" {
  type        = string
  description = "Environment short name (dev | prd)."
}

variable "vnet_address_space" {
  type        = list(string)
  description = "Address space for the virtual network. Subnet /24s are derived from the first block."
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to all resources."
  default     = {}
}
