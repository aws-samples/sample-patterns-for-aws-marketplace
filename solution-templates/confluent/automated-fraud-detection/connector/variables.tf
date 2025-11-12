############### Global Variables
variable "region" {
  description = "The region of Confluent Cloud Network"
  type        = string
  default     = "us-east-1"
}

variable "prefix" {
  description = "Prefix used in all resources created"
  type        = string
  default     = "frauddetectiondemo"
}

################ Confluent Cloud Variables
variable "confluent_cloud_api_key" {
  description = "Confluent Cloud API Key (also referred as Cloud API ID)."
  type        = string
}

variable "confluent_cloud_api_secret" {
  description = "Confluent Cloud API Secret."
  type        = string
  sensitive   = true
}

