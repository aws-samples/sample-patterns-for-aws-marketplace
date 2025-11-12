# ------------------------------------------------------
# ORGANIZATION
# ------------------------------------------------------
data "confluent_organization" "main" {}

# ------------------------------------------------------
# ENVIRONMENT
# ------------------------------------------------------

resource "confluent_environment" "staging" {
  display_name = "${var.prefix}-environment-${data.terraform_remote_state.aws_resources.outputs.env_display_id}"
  stream_governance {
    package = "ADVANCED"
  }
}

# ------------------------------------------------------
# KAFKA Cluster, Attachement and Connection
# ------------------------------------------------------
resource "confluent_kafka_cluster" "cluster" {
  display_name = "${var.prefix}-cluster-${data.terraform_remote_state.aws_resources.outputs.env_display_id}"
  availability = "SINGLE_ZONE"
  cloud        = "AWS"
  region       = var.region
  standard {}
  environment {
    id = confluent_environment.staging.id
  }
}

# ------------------------------------------------------
# SERVICE ACCOUNTS
# ------------------------------------------------------
resource "confluent_service_account" "app-manager" {
  display_name = "${var.prefix}-app-manager-${data.terraform_remote_state.aws_resources.outputs.env_display_id}"
  description  = "Service account to manage 'inventory' Kafka cluster"
}

# ------------------------------------------------------
# ROLE BINDINGS
# ------------------------------------------------------
resource "confluent_role_binding" "app-manager-kafka-cluster-admin" {
  principal   = "User:${confluent_service_account.app-manager.id}"
  role_name   = "EnvironmentAdmin"
  # TODO: replace when in production
  crn_pattern = confluent_environment.staging.resource_name
}

data "confluent_schema_registry_cluster" "sr" {

  environment {
    id = confluent_environment.staging.id
  }

  depends_on = [
    confluent_kafka_cluster.cluster
  ]
}

resource "confluent_api_key" "schema-registry-api-key" {
  display_name = "env-manager-schema-registry-api-key"
  description  = "Schema Registry API Key that is owned by 'env-manager' service account"
  owner {
    id          = confluent_service_account.app-manager.id
    api_version = confluent_service_account.app-manager.api_version
    kind        = confluent_service_account.app-manager.kind
  }
  managed_resource {
    id          = data.confluent_schema_registry_cluster.sr.id
    api_version = data.confluent_schema_registry_cluster.sr.api_version
    kind        = data.confluent_schema_registry_cluster.sr.kind
    environment {
      id = confluent_environment.staging.id
    }
  }
  depends_on = [
      confluent_service_account.app-manager
  ]
}

resource "confluent_flink_compute_pool" "flink_pool" {
  display_name     = "default"
  cloud            =  upper(data.confluent_flink_region.flink_region.cloud)
  region           =  data.confluent_flink_region.flink_region.region
  max_cfu          = 50
  environment {
    id = confluent_environment.staging.id
  }
}

data "confluent_flink_region" "flink_region" {
  cloud  = "AWS"
  region = var.region
}

resource "confluent_api_key" "flink-api-key" {
  display_name = "flink-api-key"
  description  = "Flink API Key that is owned by 'app-manager' service account"
  owner {
    id          = confluent_service_account.app-manager.id
    api_version = confluent_service_account.app-manager.api_version
    kind        = confluent_service_account.app-manager.kind
  }
  managed_resource {
    id          = data.confluent_flink_region.flink_region.id
    api_version = data.confluent_flink_region.flink_region.api_version
    kind        = data.confluent_flink_region.flink_region.kind
    environment {
      id = confluent_environment.staging.id
    }
  }
  depends_on = [
    confluent_service_account.app-manager,
    confluent_flink_compute_pool.flink_pool
  ]
}


output "confluent_details" {
  value = {
    environment_name = confluent_environment.staging.display_name
    kafka_cluster_name = confluent_kafka_cluster.cluster.display_name
    flink_pool_name = confluent_flink_compute_pool.flink_pool.display_name
  }
}