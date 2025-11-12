resource "aws_opensearch_domain" "OpenSearch" {
  domain_name = "${var.prefix}-${random_id.env_display_id.hex}"

  access_policies = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          AWS = "*"
        }
        Action = "es:*"
        Resource = "arn:aws:es:${var.region}:${data.aws_caller_identity.current.account_id}:domain/${var.prefix}-${random_id.env_display_id.hex}/*"
      }
    ]
  })


  cluster_config {
    instance_type = "t3.small.search"
    instance_count = 3
    zone_awareness_enabled = true
    zone_awareness_config {
      availability_zone_count = 3
    }
  }

  ebs_options {
    ebs_enabled = true
    volume_size = 10
    volume_type = "gp2"
  }

  node_to_node_encryption {
    enabled = true
  }

  encrypt_at_rest {
    enabled = true
  }

  domain_endpoint_options {
    enforce_https = true

    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }

  advanced_security_options {
    enabled = true
    internal_user_database_enabled = true

    master_user_options {
      master_user_name = var.opensearch_master_username
      master_user_password = var.opensearch_master_password
    }
  }

  tags = {
    Name = "${var.prefix}-opensearch-${random_id.env_display_id.hex}"
  }
}

output "opensearch_details" {
  value = {
    endpoint = "https://${aws_opensearch_domain.OpenSearch.endpoint}"
    dashboard_url = "https://${aws_opensearch_domain.OpenSearch.dashboard_endpoint}"
    username = var.opensearch_master_username
    password = var.opensearch_master_password
  }
}