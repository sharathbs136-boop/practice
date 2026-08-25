variable "subscription_id" {
  description = "Azure subscription ID, supplied with TF_VAR_subscription_id."
  type        = string
  sensitive   = true
}

variable "project" {
  type    = string
  default = "microshop"
}

variable "location" {
  type    = string
  default = "eastus"
}

variable "registry_name" {
  description = "Globally unique, alphanumeric Azure Container Registry name."
  type        = string
}
