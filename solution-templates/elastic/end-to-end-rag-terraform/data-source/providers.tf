terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0.0"
    }
    ec = {
      source  = "elastic/ec"
      version = "0.12.2"
    }
  }
}
