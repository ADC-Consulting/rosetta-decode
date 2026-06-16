terraform {
  # Partial config — the rest is supplied per environment at init via
  #   terraform init -backend-config=env/<env>.backend.hcl
  # Each env points at a different state key, so dev and prd never share state.
  backend "azurerm" {}
}
