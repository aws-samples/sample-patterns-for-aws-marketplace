# Redshift cluster security group
resource "aws_security_group" "redshift_sg" {
  name        = "${var.prefix}-redshift-sg-${random_id.env_display_id.hex}"
  description = "Security group for Redshift cluster"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 5439
    to_port     = 5439
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] 
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.prefix}-redshift-sg-${random_id.env_display_id.hex}"
  }
}

# Redshift subnet group
resource "aws_redshift_subnet_group" "redshift_subnet_group" {
  name       = "${var.prefix}-redshift-subnet-group-${random_id.env_display_id.hex}"
  subnet_ids = [for subnet in aws_subnet.public_subnets : subnet.id]

  tags = {
    Name = "${var.prefix}-redshift-subnet-group-${random_id.env_display_id.hex}"
  }
}

# Redshift cluster
resource "aws_redshift_cluster" "redshift_cluster" {
  cluster_identifier     = "${var.prefix}-redshift-cluster-${random_id.env_display_id.hex}"
  database_name         = "frauddetection"
  master_username       = "admin"
  master_password       = "Admin123456!"
  node_type            = "ra3.large"
  cluster_type         = "single-node"
  skip_final_snapshot  = true
  cluster_subnet_group_name = aws_redshift_subnet_group.redshift_subnet_group.name
  vpc_security_group_ids    = [aws_security_group.redshift_sg.id]
  availability_zone_relocation_enabled = true
  encrypted = true

  # Explicitly disable multi-AZ to prevent auto-failover conflicts
  multi_az = false

  tags = {
    Name = "${var.prefix}-redshift-cluster-${random_id.env_display_id.hex}"
  }
}

resource "aws_redshiftdata_statement" "create_schema" {
  cluster_identifier = aws_redshift_cluster.redshift_cluster.cluster_identifier
  database           = aws_redshift_cluster.redshift_cluster.database_name
  db_user            = aws_redshift_cluster.redshift_cluster.master_username
  sql                = "create schema sample authorization ${aws_redshift_cluster.redshift_cluster.master_username};"
}

resource "aws_redshiftdata_statement" "grant_usage_schema" {
  cluster_identifier = aws_redshift_cluster.redshift_cluster.cluster_identifier
  database           = aws_redshift_cluster.redshift_cluster.database_name
  db_user            = aws_redshift_cluster.redshift_cluster.master_username
  sql                = "GRANT USAGE ON SCHEMA sample TO ${aws_redshift_cluster.redshift_cluster.master_username};"

  depends_on = [aws_redshiftdata_statement.create_schema]
}

resource "aws_redshiftdata_statement" "grant_create_schema" {
  cluster_identifier = aws_redshift_cluster.redshift_cluster.cluster_identifier
  database           = aws_redshift_cluster.redshift_cluster.database_name
  db_user            = aws_redshift_cluster.redshift_cluster.master_username
  sql                = "GRANT CREATE ON SCHEMA sample TO ${aws_redshift_cluster.redshift_cluster.master_username};"

  depends_on = [aws_redshiftdata_statement.grant_usage_schema]
}

resource "aws_redshiftdata_statement" "grant_select_schema" {
  cluster_identifier = aws_redshift_cluster.redshift_cluster.cluster_identifier
  database           = aws_redshift_cluster.redshift_cluster.database_name
  db_user            = aws_redshift_cluster.redshift_cluster.master_username
  sql                = "GRANT SELECT ON ALL TABLES IN SCHEMA sample TO ${aws_redshift_cluster.redshift_cluster.master_username};"

  depends_on = [aws_redshiftdata_statement.grant_create_schema]
}

resource "aws_redshiftdata_statement" "grant_all_schema" {
  cluster_identifier = aws_redshift_cluster.redshift_cluster.cluster_identifier
  database           = aws_redshift_cluster.redshift_cluster.database_name
  db_user            = aws_redshift_cluster.redshift_cluster.master_username
  sql                = "GRANT ALL ON SCHEMA sample TO ${aws_redshift_cluster.redshift_cluster.master_username};"

  depends_on = [aws_redshiftdata_statement.grant_select_schema]
}

resource "aws_redshiftdata_statement" "grant_create_database" {
  cluster_identifier = aws_redshift_cluster.redshift_cluster.cluster_identifier
  database           = aws_redshift_cluster.redshift_cluster.database_name
  db_user            = aws_redshift_cluster.redshift_cluster.master_username
  sql                = "GRANT CREATE ON DATABASE ${aws_redshift_cluster.redshift_cluster.database_name} TO ${aws_redshift_cluster.redshift_cluster.master_username};"

  depends_on = [aws_redshiftdata_statement.grant_all_schema]
}

# Output the Redshift cluster endpoint
output "redshift_endpoint" {
  value = aws_redshift_cluster.redshift_cluster.endpoint
  description = "The connection endpoint for the Redshift cluster"
} 