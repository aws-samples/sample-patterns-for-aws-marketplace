variable "mongodbatlas_public_key" {
  description = "MongoDB Atlas API public key"
  type        = string
}

variable "mongodbatlas_private_key" {
  description = "MongoDB Atlas API private key"
  type        = string
  sensitive   = true
}

variable "mongodbatlas_org_id" {
  description = "MongoDB Atlas organization ID"
  type        = string
}
