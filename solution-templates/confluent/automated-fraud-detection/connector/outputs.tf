output "organization_id" {
  description = "The ID of the Confluent organization"
  value       = data.confluent_organization.main.id
}

output "environment_id" {
  description = "The ID of the Confluent environment"
  value       = confluent_environment.staging.id
}

output "environment_name" {
  description = "The display name of the Confluent environment (used as catalog name)"
  value       = confluent_environment.staging.display_name
}

output "kafka_cluster_name" {
  description = "The display name of the Kafka cluster (used as database name)"
  value       = confluent_kafka_cluster.cluster.display_name
}

output "flink_principal_id" {
  description = "The principal ID (service account) for Flink operations"
  value       = confluent_service_account.app-manager.id
}

output "flink_compute_pool_id" {
  description = "The ID of the Flink compute pool"
  value       = confluent_flink_compute_pool.flink_pool.id
}

output "prefix" {
  description = "The prefix used for resource naming"
  value       = var.prefix
}

output "topic_prefix" {
  description = "The topic prefix used by the Oracle connector"
  value       = "fd"
}

output "kafka_cluster_id" {
  description = "The ID of the Kafka cluster"
  value       = confluent_kafka_cluster.cluster.id
}

output "schema_registry_id" {
  description = "The ID of the Schema Registry cluster"
  value       = data.confluent_schema_registry_cluster.sr.id
}

output "schema_registry_api_key" {
  description = "The Schema Registry API key"
  value       = confluent_api_key.schema-registry-api-key.id
  sensitive   = true
}

output "schema_registry_api_secret" {
  description = "The Schema Registry API secret"
  value       = confluent_api_key.schema-registry-api-key.secret
  sensitive   = true
}

output "flink_rest_endpoint" {
  description = "The REST endpoint for the Flink region"
  value       = data.confluent_flink_region.flink_region.rest_endpoint
}

output "flink_api_key" {
  description = "The Flink API key"
  value       = confluent_api_key.flink-api-key.id
  sensitive   = true
}

output "flink_api_secret" {
  description = "The Flink API secret"
  value       = confluent_api_key.flink-api-key.secret
  sensitive   = true
}

output "service_account_id" {
  description = "The ID of the app-manager service account"
  value       = confluent_service_account.app-manager.id
}

output "service_account_api_version" {
  description = "The API version of the app-manager service account"
  value       = confluent_service_account.app-manager.api_version
}

output "service_account_kind" {
  description = "The kind of the app-manager service account"
  value       = confluent_service_account.app-manager.kind
}

output "kafka_cluster_api_version" {
  description = "The API version of the Kafka cluster"
  value       = confluent_kafka_cluster.cluster.api_version
}

output "kafka_cluster_kind" {
  description = "The kind of the Kafka cluster"
  value       = confluent_kafka_cluster.cluster.kind
}
