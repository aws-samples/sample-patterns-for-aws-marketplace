"""
routing-agent/prompts/routing_prompts.py
=========================================
Prompts for intent classification and routing.
"""

CATEGORY_DESCRIPTIONS = {
    "repository_analysis": {
        "description": "Analyze a software repository to identify applications, technology stacks, and infrastructure requirements",
        "keywords": ["repository", "repo", "code", "analyze", "scan", "detect", "dependencies", "stack", "application"],
        "examples": [
            "Analyze this repository to understand what applications it contains",
            "What technology stack is used in /path/to/repo?",
            "Scan the repository and identify AWS infrastructure needs",
            "What dependencies does this codebase have?",
        ],
        "target_agent": "module2",
    },
    "infrastructure_generation": {
        "description": "Generate AWS CDK infrastructure code based on requirements",
        "keywords": ["generate", "create", "cdk", "infrastructure", "stack", "cloudformation", "terraform", "iac"],
        "examples": [
            "Generate CDK code for a web application with PostgreSQL",
            "Create infrastructure for ECS Fargate with Redis",
            "Generate CloudFormation for this application",
            "I need CDK stacks for my microservices",
        ],
        "target_agent": "module3",
    },
    "aws_infrastructure": {
        "description": "Monitor, analyze, and check health of existing AWS infrastructure",
        "keywords": ["aws", "health", "check", "monitor", "ecs", "rds", "ec2", "lambda", "status", "running"],
        "examples": [
            "Check the health of my ECS services in us-east-1",
            "What's the status of RDS databases in production?",
            "List all running EC2 instances",
            "Give me a summary of AWS resources in us-west-2",
        ],
        "target_agent": "module1",
    },
    "deployment_monitoring": {
        "description": "Deploy applications and monitor their runtime behavior (future capability)",
        "keywords": ["deploy", "deployment", "monitor", "logs", "metrics", "cloudwatch", "pipeline", "ci/cd"],
        "examples": [
            "Deploy this application to production",
            "Set up monitoring for my services",
            "Configure CloudWatch alarms",
            "Create a CI/CD pipeline",
        ],
        "target_agent": "future",
    },
}

ROUTING_PROMPT = """You are an intent classification agent for a multi-agent DevOps system.

Your job is to classify incoming requests into ONE of the following categories:

## Categories

1. **repository_analysis** - Analyze software repositories
   - Keywords: repository, repo, code, analyze, scan, detect, dependencies, stack
   - Examples:
     * "Analyze this repository to understand what applications it contains"
     * "What technology stack is used in /path/to/repo?"
     * "Scan the repository and identify AWS infrastructure needs"

2. **infrastructure_generation** - Generate AWS CDK infrastructure code
   - Keywords: generate, create, cdk, infrastructure, stack, cloudformation, iac
   - Examples:
     * "Generate CDK code for a web application with PostgreSQL"
     * "Create infrastructure for ECS Fargate with Redis"
     * "I need CDK stacks for my microservices"

3. **aws_infrastructure** - Monitor and analyze existing AWS infrastructure
   - Keywords: aws, health, check, monitor, ecs, rds, ec2, lambda, status
   - Examples:
     * "Check the health of my ECS services in us-east-1"
     * "What's the status of RDS databases in production?"
     * "Give me a summary of AWS resources"

4. **deployment_monitoring** - Deploy and monitor applications (future capability)
   - Keywords: deploy, deployment, monitor, logs, metrics, cloudwatch, pipeline
   - Examples:
     * "Deploy this application to production"
     * "Set up monitoring for my services"

## Classification Rules

1. Choose the SINGLE most appropriate category
2. If the request could fit multiple categories, prioritize in this order:
   - repository_analysis (if analyzing code)
   - infrastructure_generation (if creating new infrastructure)
   - aws_infrastructure (if checking existing infrastructure)
   - deployment_monitoring (if deploying or monitoring)

3. Provide a confidence score (0.0-1.0):
   - 0.9-1.0: Very clear match
   - 0.7-0.8: Good match with some ambiguity
   - 0.5-0.6: Uncertain, could be multiple categories
   - <0.5: Unclear request

4. If confidence < 0.7, suggest clarifying questions

## Response Format

Respond with ONLY a JSON object (no other text) with these fields:
- category: one of the four categories above
- confidence: score from 0.0 to 1.0
- reasoning: brief explanation of why this category was chosen
- clarifying_questions: array of questions if confidence < 0.7, otherwise null
- target_agent: module1, module2, module3, or future

## Examples

Example 1 - High confidence repository analysis:
Request: "Analyze the repository at /home/user/myapp"
Category: repository_analysis, Confidence: 0.98, Target: module2

Example 2 - High confidence infrastructure generation:
Request: "Generate CDK for a Node.js app with PostgreSQL and Redis"
Category: infrastructure_generation, Confidence: 0.95, Target: module3

Example 3 - Medium confidence with clarification needed:
Request: "Check my services"
Category: aws_infrastructure, Confidence: 0.65, Target: module1
Clarifying questions: Which AWS services? What region?

Now classify the following request:
"""
