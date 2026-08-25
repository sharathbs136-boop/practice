output "acr_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "aks_name" {
  value = azurerm_kubernetes_cluster.main.name
}

output "resource_group" {
  value = azurerm_resource_group.main.name
}

output "aks_kube_config_command" {
  value = "az aks get-credentials --resource-group ${azurerm_resource_group.main.name} --name ${azurerm_kubernetes_cluster.main.name} --overwrite-existing"
}
