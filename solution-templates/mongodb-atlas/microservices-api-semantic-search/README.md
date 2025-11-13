# Microservices API with Semantic Search using MongoDB Atlas and Amazon Bedrock

## Overview
This solution template deploys a complete microservices architecture with semantic search capabilities, leveraging MongoDB Atlas for data storage and vector search, combined with Amazon Bedrock for AI-powered embeddings.

### What This Solution Deploys

This template automates the deployment of:

1. **MongoDB Atlas Cluster** - M0 free tier cluster with vector search capabilities
2. **MongoDB Data API** - Serverless REST API for database operations
3. **Semantic Search Service** - Lambda function integrating Bedrock embeddings with MongoDB vector search
4. **Todos Microservice** - Complete CRUD API for task management
5. **API Gateway** - Unified REST API endpoint with IAM authentication
6. **Sample Data** - Pre-loaded travel dataset with vector embeddings

### Architecture

The solution implements a modern microservices pattern:
- MongoDB Atlas provides the database layer with built-in vector search
- AWS Lambda functions implement business logic
- Amazon Bedrock generates embeddings for semantic search
- API Gateway provides a secure, scalable API layer
- All components use IAM authentication for security

### Prerequisites

- AWS Account with appropriate permissions
- MongoDB Atlas subscription ([Subscribe on AWS Marketplace](https://aws.amazon.com/marketplace/pp/prodview-pp445qepfdy34))
- Terraform installed (version 1.0+)
- AWS CLI configured
- MongoDB Atlas API keys ([How to create API keys](https://www.mongodb.com/docs/atlas/configure-api-access/#std-label-atlas-admin-api-access))

### Quick Start

1. **Set up MongoDB Atlas credentials**
   ```bash
   export MONGODB_ATLAS_PUBLIC_KEY="your-public-key"
   export MONGODB_ATLAS_PRIVATE_KEY="your-private-key"
   export MONGODB_ATLAS_ORG_ID="your-org-id"
   ```

2. **Deploy the solution**
   ```bash
   terraform init
   terraform apply
   ```

3. **Test the APIs**
   ```bash
   # Test semantic search
   python3 semantic_search_test.py
   
   # Test todos service
   python3 todos_service_test.py
   ```

### What Gets Created

- **MongoDB Atlas Resources**
  - Project: "Application Modernization Workshop"
  - Cluster: "ApplicationDB" (M0 free tier)
  - Database user with read/write permissions
  - Vector search index on travel data

- **AWS Resources**
  - 2 Lambda functions (semantic search, todos service)
  - API Gateway REST API
  - IAM roles and policies
  - CloudWatch log groups

### API Endpoints

After deployment, you'll have access to:

**Semantic Search API**
```bash
POST /search
{
  "query": "beach vacation",
  "limit": 5
}
```

**Todos API**
```bash
GET    /todos          # List all todos
POST   /todos          # Create todo
PUT    /todos/{id}     # Update todo
DELETE /todos/{id}     # Delete todo
```

### Cost Estimate

- MongoDB Atlas M0: **Free**
- AWS Lambda: **Free tier eligible** (~$0.20/month after free tier)
- API Gateway: **Free tier eligible** (~$3.50/month per million requests after free tier)
- Data transfer: Minimal costs

**Estimated monthly cost: $0-5** (within AWS free tier)

### Cleanup

To remove all resources:
```bash
terraform destroy
```

### Learn More

- [MongoDB Atlas Vector Search Documentation](https://www.mongodb.com/docs/atlas/atlas-vector-search/)
- [Amazon Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)
- [Building Microservices with MongoDB](https://www.mongodb.com/microservices)

### Support

For issues or questions:
- MongoDB Atlas: [Support Portal](https://support.mongodb.com/)
- AWS: [AWS Support](https://aws.amazon.com/support/)
- GitHub Issues: [Report an issue](https://github.com/aws-samples/sample-patterns-for-aws-marketplace/issues)
