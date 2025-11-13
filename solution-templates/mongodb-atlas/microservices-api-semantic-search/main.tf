terraform {
  required_providers {
    mongodbatlas = {
      source = "mongodb/mongodbatlas"
    }
    aws = {
      source = "hashicorp/aws"
    }
    random = {
      source = "hashicorp/random"
    }
    null = {
      source = "hashicorp/null"
    }
    local = {
      source = "hashicorp/local"
    }
  }
}

provider "mongodbatlas" {
  public_key  = var.mongodbatlas_public_key
  private_key = var.mongodbatlas_private_key
}

provider "aws" {
  # Region will be detected from environment/profile automatically
}

# Data sources for dynamic region detection
data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# Local values for region mapping
locals {
  mongodb_region_map = {
    "us-east-1" = "US_EAST_1"
    "us-west-2" = "US_WEST_2"
  }
}

resource "mongodbatlas_project" "workshop_project" {
  name   = "Application Modernization Workshop"
  org_id = var.mongodbatlas_org_id
}

resource "mongodbatlas_cluster" "application_db" {
  project_id   = mongodbatlas_project.workshop_project.id
  name         = "ApplicationDB"
  
  provider_name               = "TENANT"
  backing_provider_name       = "AWS"
  provider_region_name        = local.mongodb_region_map[data.aws_region.current.name]
  provider_instance_size_name = "M0"
}

resource "random_password" "database_password" {
  length  = 16
  special = false
}

resource "mongodbatlas_database_user" "api_user" {
  username           = "api_user"
  password           = random_password.database_password.result
  project_id         = mongodbatlas_project.workshop_project.id
  auth_database_name = "admin"

  roles {
    role_name     = "readWriteAnyDatabase"
    database_name = "admin"
  }
}

resource "mongodbatlas_project_ip_access_list" "workshop_access" {
  project_id = mongodbatlas_project.workshop_project.id
  cidr_block = "0.0.0.0/0"
  comment    = "Temporary allowlisting for the AWS workshop"
}


# Deploy MongoDB Data API from Serverless Application Repository
resource "aws_serverlessapplicationrepository_cloudformation_stack" "mongodb_data_api" {
  name           = "mongodb-data-api-stack"
  application_id = "arn:aws:serverlessrepo:us-east-1:979559056307:applications/MongoDB-DataAPI"
  semantic_version = "1.0.1"
  
  parameters = {
    AtlasConnectionString = local.connection_string
  }

  capabilities = [
    "CAPABILITY_IAM",
    "CAPABILITY_RESOURCE_POLICY"
  ]

  depends_on = [mongodbatlas_cluster.application_db]
}

locals {
  connection_string = replace(mongodbatlas_cluster.application_db.connection_strings[0].standard_srv, "mongodb+srv://", "mongodb+srv://${mongodbatlas_database_user.api_user.username}:${random_password.database_password.result}@")
}

# Generate test script with dynamic API URL
resource "local_file" "test_script" {
  content = templatefile("${path.module}/test_api_template.py", {
    api_url = aws_serverlessapplicationrepository_cloudformation_stack.mongodb_data_api.outputs["MDBApiUrl"]
  })
  filename = "${path.module}/test_api.py"
  
  depends_on = [aws_serverlessapplicationrepository_cloudformation_stack.mongodb_data_api]
}

# Generate data import script with dynamic MongoDB connection string
resource "local_file" "import_script" {
  content = templatefile("${path.module}/mdb_import_template.py", {
    mongodb_connection_string = local.connection_string
  })
  filename = "${path.module}/mdb_import.py"
  
  depends_on = [mongodbatlas_cluster.application_db]
}

# Download sample data
resource "null_resource" "download_data" {
  provisioner "local-exec" {
    command = "wget -O anthropic-travel-agency.trip_recommendations.csv https://raw.githubusercontent.com/mongodb-partners/QS-Anthropic-1/refs/heads/main/anthropic-travel-agency.trip_recommendations.csv --no-check-certificate"
    working_dir = path.module
  }

  # Only download if file doesn't exist
  provisioner "local-exec" {
    command = "test -f anthropic-travel-agency.trip_recommendations.csv || wget -O anthropic-travel-agency.trip_recommendations.csv https://raw.githubusercontent.com/mongodb-partners/QS-Anthropic-1/refs/heads/main/anthropic-travel-agency.trip_recommendations.csv --no-check-certificate"
    working_dir = path.module
  }

  depends_on = [mongodbatlas_cluster.application_db]
}

# Import data to MongoDB
resource "null_resource" "data_import" {
  depends_on = [
    mongodbatlas_cluster.application_db,
    mongodbatlas_database_user.api_user,
    mongodbatlas_project_ip_access_list.workshop_access,
    local_file.import_script,
    null_resource.download_data
  ]

  provisioner "local-exec" {
    command = "pip3 install pymongo && python3 mdb_import.py"
    working_dir = path.module
  }

  # Trigger re-run if the import script changes
  triggers = {
    script_hash = filemd5("${path.module}/mdb_import_template.py")
    connection_string = local.connection_string
  }
}

# Create vector search index after data is imported
resource "mongodbatlas_search_index" "travel_vector_index" {
  depends_on = [null_resource.data_import]
  
  project_id      = mongodbatlas_project.workshop_project.id
  cluster_name    = mongodbatlas_cluster.application_db.name
  
  name            = "vector_index"
  database        = "travel"
  collection_name = "asia"
  type            = "vectorSearch"
  
  fields = jsonencode([
    {
      type = "vector"
      path = "details_embedding"
      numDimensions = 1536
      similarity = "cosine"
    }
  ])
}

output "connection_string" {
  value     = local.connection_string
  sensitive = true
}

output "api_gateway_url" {
  value = aws_serverlessapplicationrepository_cloudformation_stack.mongodb_data_api.outputs["MDBApiUrl"]
}

output "cluster_id" {
  value = mongodbatlas_cluster.application_db.cluster_id
}

output "project_id" {
  value = mongodbatlas_project.workshop_project.id
}

output "cluster_name" {
  value = mongodbatlas_cluster.application_db.name
}

output "vector_index_name" {
  value = mongodbatlas_search_index.travel_vector_index.name
}

output "vector_index_status" {
  value = mongodbatlas_search_index.travel_vector_index.status
}

# ===================================
# Semantic Search Service Resources
# ===================================

# IAM role for semantic search Lambda
resource "aws_iam_role" "semantic_search_lambda_role" {
  name = "semantic-search-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# IAM policy for semantic search Lambda
resource "aws_iam_role_policy" "semantic_search_lambda_policy" {
  name = "semantic-search-lambda-policy"
  role = aws_iam_role.semantic_search_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/amazon.titan-embed-text-v1"
      },
      {
        Effect = "Allow"
        Action = [
          "execute-api:Invoke"
        ]
        Resource = "arn:aws:execute-api:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:*/*"
      }
    ]
  })
}

# Generate Lambda function from template
resource "local_file" "semantic_search_lambda" {
  content = templatefile("${path.module}/semantic_search_lambda_template.py", {
    mongodb_api_url = aws_serverlessapplicationrepository_cloudformation_stack.mongodb_data_api.outputs["MDBApiUrl"]
  })
  filename = "${path.module}/semantic_search_lambda.py"
  
  depends_on = [aws_serverlessapplicationrepository_cloudformation_stack.mongodb_data_api]
}

# Package Lambda function
data "archive_file" "semantic_search_lambda_zip" {
  type        = "zip"
  source_file = local_file.semantic_search_lambda.filename
  output_path = "${path.module}/semantic_search_lambda.zip"
  
  depends_on = [local_file.semantic_search_lambda]
}

# Lambda function
resource "aws_lambda_function" "semantic_search" {
  filename         = data.archive_file.semantic_search_lambda_zip.output_path
  function_name    = "semantic-search-service"
  role            = aws_iam_role.semantic_search_lambda_role.arn
  handler         = "semantic_search_lambda.lambda_handler"
  source_code_hash = data.archive_file.semantic_search_lambda_zip.output_base64sha256
  runtime         = "python3.12"
  timeout         = 30
  
  environment {
    variables = {
      MONGODB_API_URL = aws_serverlessapplicationrepository_cloudformation_stack.mongodb_data_api.outputs["MDBApiUrl"]
    }
  }
  
  depends_on = [
    aws_iam_role_policy.semantic_search_lambda_policy,
    data.archive_file.semantic_search_lambda_zip
  ]
}

# API Gateway REST API
resource "aws_api_gateway_rest_api" "semantic_search_api" {
  name        = "semantic-search-api"
  description = "API Gateway for Semantic Search Service"
  
  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

# API Gateway resource for /search
resource "aws_api_gateway_resource" "search_resource" {
  rest_api_id = aws_api_gateway_rest_api.semantic_search_api.id
  parent_id   = aws_api_gateway_rest_api.semantic_search_api.root_resource_id
  path_part   = "search"
}

# API Gateway method for POST /search
resource "aws_api_gateway_method" "search_post" {
  rest_api_id   = aws_api_gateway_rest_api.semantic_search_api.id
  resource_id   = aws_api_gateway_resource.search_resource.id
  http_method   = "POST"
  authorization = "AWS_IAM"
}

# API Gateway integration with Lambda
resource "aws_api_gateway_integration" "search_lambda_integration" {
  rest_api_id = aws_api_gateway_rest_api.semantic_search_api.id
  resource_id = aws_api_gateway_resource.search_resource.id
  http_method = aws_api_gateway_method.search_post.http_method
  
  integration_http_method = "POST"
  type                   = "AWS_PROXY"
  uri                    = aws_lambda_function.semantic_search.invoke_arn
}

# Lambda permission for API Gateway
resource "aws_lambda_permission" "api_gateway_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.semantic_search.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.semantic_search_api.execution_arn}/*/*"
}

# API Gateway deployment
resource "aws_api_gateway_deployment" "semantic_search_deployment" {
  rest_api_id = aws_api_gateway_rest_api.semantic_search_api.id
  
  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.search_resource.id,
      aws_api_gateway_method.search_post.id,
      aws_api_gateway_integration.search_lambda_integration.id,
      aws_api_gateway_resource.todos_resource.id,
      aws_api_gateway_resource.todos_id_resource.id,
      aws_api_gateway_method.todos_get.id,
      aws_api_gateway_method.todos_post.id,
      aws_api_gateway_method.todos_id_get.id,
      aws_api_gateway_method.todos_id_put.id,
      aws_api_gateway_method.todos_id_delete.id,
      aws_api_gateway_integration.todos_get_integration.id,
      aws_api_gateway_integration.todos_post_integration.id,
      aws_api_gateway_integration.todos_id_get_integration.id,
      aws_api_gateway_integration.todos_id_put_integration.id,
      aws_api_gateway_integration.todos_id_delete_integration.id,
    ]))
  }
  
  lifecycle {
    create_before_destroy = true
  }
  
  depends_on = [
    aws_api_gateway_integration.search_lambda_integration,
    aws_api_gateway_integration.todos_get_integration,
    aws_api_gateway_integration.todos_post_integration,
    aws_api_gateway_integration.todos_id_get_integration,
    aws_api_gateway_integration.todos_id_put_integration,
    aws_api_gateway_integration.todos_id_delete_integration
  ]
}

# API Gateway stage
resource "aws_api_gateway_stage" "semantic_search_prod" {
  deployment_id = aws_api_gateway_deployment.semantic_search_deployment.id
  rest_api_id   = aws_api_gateway_rest_api.semantic_search_api.id
  stage_name    = "prod"
}

# Generate test script for semantic search API
resource "local_file" "semantic_search_test_script" {
  content = templatefile("${path.module}/semantic_search_test_template.py", {
    api_url = aws_api_gateway_stage.semantic_search_prod.invoke_url
  })
  filename = "${path.module}/semantic_search_test.py"
  
  depends_on = [aws_api_gateway_stage.semantic_search_prod]
}

# Additional outputs for semantic search service
output "semantic_search_api_url" {
  value       = aws_api_gateway_stage.semantic_search_prod.invoke_url
  description = "URL of the Semantic Search API Gateway"
}

output "semantic_search_lambda_arn" {
  value       = aws_lambda_function.semantic_search.arn
  description = "ARN of the Semantic Search Lambda function"
}

# ===================================
# Todos Service Resources
# ===================================

# IAM role for Todos Lambda
resource "aws_iam_role" "todos_lambda_role" {
  name = "todos-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# IAM policy for Todos Lambda
resource "aws_iam_role_policy" "todos_lambda_policy" {
  name = "todos-lambda-policy"
  role = aws_iam_role.todos_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "execute-api:Invoke"
        ]
        Resource = "arn:aws:execute-api:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:*/*"
      }
    ]
  })
}

# Generate Lambda function from template
resource "local_file" "todos_lambda" {
  content = templatefile("${path.module}/todos_service_lambda_template.py", {
    mongodb_api_url = aws_serverlessapplicationrepository_cloudformation_stack.mongodb_data_api.outputs["MDBApiUrl"]
  })
  filename = "${path.module}/todos_service_lambda.py"
  
  depends_on = [aws_serverlessapplicationrepository_cloudformation_stack.mongodb_data_api]
}

# Package Lambda function
data "archive_file" "todos_lambda_zip" {
  type        = "zip"
  source_file = local_file.todos_lambda.filename
  output_path = "${path.module}/todos_service_lambda.zip"
  
  depends_on = [local_file.todos_lambda]
}

# Lambda function
resource "aws_lambda_function" "todos_service" {
  filename         = data.archive_file.todos_lambda_zip.output_path
  function_name    = "todos-service"
  role            = aws_iam_role.todos_lambda_role.arn
  handler         = "todos_service_lambda.lambda_handler"
  source_code_hash = data.archive_file.todos_lambda_zip.output_base64sha256
  runtime         = "python3.12"
  timeout         = 30
  
  environment {
    variables = {
      MONGODB_API_URL = aws_serverlessapplicationrepository_cloudformation_stack.mongodb_data_api.outputs["MDBApiUrl"]
    }
  }
  
  depends_on = [
    aws_iam_role_policy.todos_lambda_policy,
    data.archive_file.todos_lambda_zip
  ]
}

# API Gateway resource for /todos
resource "aws_api_gateway_resource" "todos_resource" {
  rest_api_id = aws_api_gateway_rest_api.semantic_search_api.id
  parent_id   = aws_api_gateway_rest_api.semantic_search_api.root_resource_id
  path_part   = "todos"
}

# API Gateway resource for /todos/{id}
resource "aws_api_gateway_resource" "todos_id_resource" {
  rest_api_id = aws_api_gateway_rest_api.semantic_search_api.id
  parent_id   = aws_api_gateway_resource.todos_resource.id
  path_part   = "{id}"
}

# API Gateway methods for /todos

# GET /todos
resource "aws_api_gateway_method" "todos_get" {
  rest_api_id   = aws_api_gateway_rest_api.semantic_search_api.id
  resource_id   = aws_api_gateway_resource.todos_resource.id
  http_method   = "GET"
  authorization = "AWS_IAM"
}

resource "aws_api_gateway_integration" "todos_get_integration" {
  rest_api_id = aws_api_gateway_rest_api.semantic_search_api.id
  resource_id = aws_api_gateway_resource.todos_resource.id
  http_method = aws_api_gateway_method.todos_get.http_method
  
  integration_http_method = "POST"
  type                   = "AWS_PROXY"
  uri                    = aws_lambda_function.todos_service.invoke_arn
}

# POST /todos
resource "aws_api_gateway_method" "todos_post" {
  rest_api_id   = aws_api_gateway_rest_api.semantic_search_api.id
  resource_id   = aws_api_gateway_resource.todos_resource.id
  http_method   = "POST"
  authorization = "AWS_IAM"
}

resource "aws_api_gateway_integration" "todos_post_integration" {
  rest_api_id = aws_api_gateway_rest_api.semantic_search_api.id
  resource_id = aws_api_gateway_resource.todos_resource.id
  http_method = aws_api_gateway_method.todos_post.http_method
  
  integration_http_method = "POST"
  type                   = "AWS_PROXY"
  uri                    = aws_lambda_function.todos_service.invoke_arn
}

# API Gateway methods for /todos/{id}

# GET /todos/{id}
resource "aws_api_gateway_method" "todos_id_get" {
  rest_api_id   = aws_api_gateway_rest_api.semantic_search_api.id
  resource_id   = aws_api_gateway_resource.todos_id_resource.id
  http_method   = "GET"
  authorization = "AWS_IAM"
}

resource "aws_api_gateway_integration" "todos_id_get_integration" {
  rest_api_id = aws_api_gateway_rest_api.semantic_search_api.id
  resource_id = aws_api_gateway_resource.todos_id_resource.id
  http_method = aws_api_gateway_method.todos_id_get.http_method
  
  integration_http_method = "POST"
  type                   = "AWS_PROXY"
  uri                    = aws_lambda_function.todos_service.invoke_arn
}

# PUT /todos/{id}
resource "aws_api_gateway_method" "todos_id_put" {
  rest_api_id   = aws_api_gateway_rest_api.semantic_search_api.id
  resource_id   = aws_api_gateway_resource.todos_id_resource.id
  http_method   = "PUT"
  authorization = "AWS_IAM"
}

resource "aws_api_gateway_integration" "todos_id_put_integration" {
  rest_api_id = aws_api_gateway_rest_api.semantic_search_api.id
  resource_id = aws_api_gateway_resource.todos_id_resource.id
  http_method = aws_api_gateway_method.todos_id_put.http_method
  
  integration_http_method = "POST"
  type                   = "AWS_PROXY"
  uri                    = aws_lambda_function.todos_service.invoke_arn
}

# DELETE /todos/{id}
resource "aws_api_gateway_method" "todos_id_delete" {
  rest_api_id   = aws_api_gateway_rest_api.semantic_search_api.id
  resource_id   = aws_api_gateway_resource.todos_id_resource.id
  http_method   = "DELETE"
  authorization = "AWS_IAM"
}

resource "aws_api_gateway_integration" "todos_id_delete_integration" {
  rest_api_id = aws_api_gateway_rest_api.semantic_search_api.id
  resource_id = aws_api_gateway_resource.todos_id_resource.id
  http_method = aws_api_gateway_method.todos_id_delete.http_method
  
  integration_http_method = "POST"
  type                   = "AWS_PROXY"
  uri                    = aws_lambda_function.todos_service.invoke_arn
}

# Lambda permission for API Gateway to invoke Todos Lambda
resource "aws_lambda_permission" "todos_api_gateway_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.todos_service.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.semantic_search_api.execution_arn}/*/*"
}

# Generate test script for Todos Service API
resource "local_file" "todos_test_script" {
  content = templatefile("${path.module}/todos_service_test_template.py", {
    api_url = aws_api_gateway_stage.semantic_search_prod.invoke_url
  })
  filename = "${path.module}/todos_service_test.py"
  
  depends_on = [aws_api_gateway_stage.semantic_search_prod]
}

# Additional outputs for Todos service
output "todos_lambda_arn" {
  value       = aws_lambda_function.todos_service.arn
  description = "ARN of the Todos Service Lambda function"
}
