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

# Data source to read AWS resources terraform state
data "terraform_remote_state" "aws_resources" {
  backend = "local"
  config = {
    path = "../aws_resources/terraform.tfstate"
  }
}
