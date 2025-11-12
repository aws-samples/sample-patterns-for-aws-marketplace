terraform {
    required_providers {
        confluent = {
          source  = "confluentinc/confluent"
          version = "2.12.0"
        }
    }
}

provider "confluent" {
  cloud_api_key    = var.confluent_cloud_api_key
  cloud_api_secret = var.confluent_cloud_api_secret
}

data "terraform_remote_state" "connector" {
  backend = "local"
  config = {
    path = "${path.module}/../connector/terraform.tfstate"
  }
}

data "terraform_remote_state" "aws_resources" {
  backend = "local"
  config = {
    path = "${path.module}/../aws_resources/terraform.tfstate"
  }
}
