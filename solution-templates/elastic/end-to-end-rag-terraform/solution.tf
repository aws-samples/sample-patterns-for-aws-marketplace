terraform {
  required_providers {
    ec = {
      source  = "elastic/ec"
      version = "0.12.2"
    }
  }
}

provider "ec" {
  apikey = var.elastic_cloud_api_key
}

module "vpc" {
    source = "terraform-aws-modules/vpc/aws"
    version = "6.0.1"
    name = "marketplace-elastic"
    cidr = "10.0.0.0/16"
    azs = ["us-east-1b", "us-east-1c", "us-east-1d"]
    private_subnets = ["10.0.10.0/24", "10.0.20.0/24", "10.0.30.0/24"]
    public_subnets = ["10.0.40.0/24", "10.0.50.0/24", "10.0.60.0/24"]
    enable_nat_gateway = true
    enable_dns_support = true
    enable_dns_hostnames = true
    tags = {
        Name = "marketplace-elastic"
    }
}

resource "aws_security_group_rule" "allow_all_ingress" {
    type = "ingress"
    from_port = 0
    to_port = 0
    protocol = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    security_group_id = module.vpc.default_security_group_id
}

resource "aws_security_group_rule" "allow_all_egress" {
    type = "egress"
    from_port = 0
    to_port = 0
    protocol = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    security_group_id = module.vpc.default_security_group_id
}

module "private-link" {
    source = "./private-link"
    vpc_id = module.vpc.vpc_id
    deployment_id = var.deployment_id
    subnet_ids = module.vpc.private_subnets
}

module "data-source" {
    source = "./data-source"
    deployment_id = var.deployment_id
    vpc_id = module.vpc.vpc_id
    route_table_ids = [module.vpc.vpc_main_route_table_id]
    security_group_ids = [module.vpc.default_security_group_id]
}

module "lambda-vectorizer" {
    source = "./lambda-vectorizer"
    vpc_id = module.vpc.vpc_id
    elasticsearch_connection_secret = var.elasticsearch_connection_secret
    elasticsearch_private_https_endpoint = module.private-link.elasticsearch_private_https_endpoint
    s3_bucket = module.data-source.bucket_name
    vpc_subnet_ids = module.vpc.private_subnets
    vpc_security_group_ids = [module.vpc.default_security_group_id]
    bucket_id = module.data-source.bucket_name
}

module "lambda-agent" {
    source = "./lambda-agent"
    vpc_id = module.vpc.vpc_id
    elasticsearch_connection_secret = var.elasticsearch_connection_secret
    elasticsearch_private_https_endpoint = module.private-link.elasticsearch_private_https_endpoint
    vpc_subnet_ids = module.vpc.private_subnets
    vpc_security_group_ids = [module.vpc.default_security_group_id]
}

module "api-gateway" {
    source = "./api-gateway"
    lambda_agent_function_name = module.lambda-agent.function_name
    lambda_agent_function_arn = module.lambda-agent.function_arn
}