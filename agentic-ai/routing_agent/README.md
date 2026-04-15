# Routing Agent: Intent Classification & Request Routing

Simple intent classification agent for routing requests to specialist agents.

## Overview

The routing agent classifies incoming user requests and routes them to the appropriate specialist agent (Module 1, Module 2, or Module 3). It uses a single LLM call for efficient classification without a full agent loop.

## Categories

| Category | Description | Target Agent | Port |
|----------|-------------|--------------|------|
| `repository_analysis` | Analyze software repositories | Module 2 | 8081 |
| `infrastructure_generation` | Generate AWS CDK infrastructure code | Module 3 | 8082 |
| `aws_infrastructure` | Monitor and analyze existing AWS infrastructure | Module 1 | 8080 |
| `deployment_monitoring` | Deploy and monitor applications | Future | - |

## Quick Start

```bash
# Start routing agent server
python routing-agent/app.py

# Classify a request
curl -X POST http://localhost:8083/route \
  -H "Content-Type: application/json" \
  -d '{"request": "Analyze my repository at /home/user/app"}'

# Get available categories
curl http://localhost:8083/categories
```

## Usage

### Python API

```python
from routing_agent.agent import classify_intent, route_request

# Simple classification
result = classify_intent("Generate CDK for a web app")
print(f"Category: {result['category']}")
print(f"Confidence: {result['confidence']}")
print(f"Target: {result['target_agent']}")

# Full routing with suggested action
routing = route_request("Analyze my repository")
print(f"Action: {routing['suggested_action']}")  # "route", "clarify", or "reject"
print(f"URL: {routing['target_url']}")
```

### Batch Classification

```python
from routing_agent.agent import classify_batch

requests = [
    "Analyze repository at /path/to/repo",
    "Generate CDK for ECS Fargate",
    "Check AWS health in us-east-1",
]

results = classify_batch(requests)
for r in results:
    print(f"{r['category']}: {r['confidence']:.2f}")
```

## Classification Logic

### Confidence Thresholds

- **≥ 0.7**: High confidence → Route to target agent
- **0.5-0.7**: Medium confidence → Ask clarifying questions
- **< 0.5**: Low confidence → Reject or ask for rephrasing

### Example Classifications

```python
# High confidence - repository analysis
"Analyze the repository at /home/user/myapp"
→ category: repository_analysis, confidence: 0.98

# High confidence - infrastructure generation
"Generate CDK code for a Node.js app with PostgreSQL"
→ category: infrastructure_generation, confidence: 0.95

# Medium confidence - needs clarification
"Check my services"
→ category: aws_infrastructure, confidence: 0.65
→ clarifying_questions: ["Which AWS services?", "What region?"]

# Low confidence - unclear
"Do something with my stuff"
→ category: unknown, confidence: 0.2
→ suggested_action: reject
```

## HTTP API

### Endpoints

#### `POST /route`

Full routing with suggested action.

**Request:**
```json
{
  "request": "User's request text"
}
```

**Response:**
```json
{
  "status": "success",
  "routing": {
    "category": "infrastructure_generation",
    "confidence": 0.95,
    "reasoning": "Clear request to generate infrastructure code",
    "target_agent": "module3",
    "target_url": "http://localhost:8082",
    "suggested_action": "route",
    "action_message": "Route to module3"
  }
}
```

#### `POST /classify`

Classification only (no routing metadata).

**Request:**
```json
{
  "request": "User's request text"
}
```

**Response:**
```json
{
  "status": "success",
  "classification": {
    "category": "repository_analysis",
    "confidence": 0.92,
    "reasoning": "Request to analyze a repository",
    "target_agent": "module2",
    "target_url": "http://localhost:8081"
  }
}
```

#### `GET /categories`

List available categories and their descriptions.

#### `GET /ping`

Health check endpoint.

## Architecture

### Model Configuration

- **Model**: Claude Sonnet 4 via Amazon Bedrock
- **Temperature**: 0.0 (deterministic classification)
- **Max Tokens**: 1024 (classification is short)
- **Framework**: LangChain (ChatBedrock + StrOutputParser)

### Classification Prompt

The routing agent uses a carefully crafted prompt that:
- Defines all categories with keywords and examples
- Provides classification rules and priority order
- Specifies confidence scoring guidelines
- Requests structured JSON output

### No Agent Loop

Unlike Module 1, 2, and 3, the routing agent does NOT use a full agent loop. It's a single-shot classification:

```python
# Simple chain (not an agent)
prompt = ChatPromptTemplate.from_messages([
    ("system", ROUTING_PROMPT),
    ("user", "{request}"),
])
chain = prompt | model | StrOutputParser()
response = chain.invoke({"request": user_request})
```

This is more efficient for classification tasks that don't require tool use.

## Configuration

### Environment Variables

```bash
# Agent URLs (defaults shown)
MODULE1_URL=http://localhost:8080
MODULE2_URL=http://localhost:8081
MODULE3_URL=http://localhost:8082

# Routing agent server
ROUTING_PORT=8083
ROUTING_HOST=0.0.0.0
ROUTING_VERBOSE=false

# AWS Bedrock
AWS_REGION=us-east-1
```

## Testing

```bash
# Run routing agent tests
AGENT_MOCK_REPO=true pytest tests/test_routing_agent.py -v

# Test classification accuracy
AGENT_MOCK_REPO=true pytest tests/test_routing_agent.py::test_classify_repository_analysis -v
```

## Integration Example

```python
from routing_agent.agent import route_request

# User request comes in
user_request = "Analyze my repository and generate infrastructure"

# Classify and route
routing = route_request(user_request)

if routing["suggested_action"] == "route":
    # Forward to target agent
    target_url = routing["target_url"]
    target_agent = routing["target_agent"]
    
    if target_agent == "module2":
        from module2.agent import analyze_repository
        result = analyze_repository(user_request)
    elif target_agent == "module3":
        from module3.agent import generate_infrastructure
        result = generate_infrastructure(user_request)
    
elif routing["suggested_action"] == "clarify":
    # Ask clarifying questions
    questions = routing.get("clarifying_questions", [])
    print(f"Please clarify: {questions}")

else:
    # Reject unclear request
    print("Unable to understand request. Please rephrase.")
```

## Project Structure

```
routing-agent/
├── agent.py              # Classification and routing logic
├── app.py                # HTTP server
├── config/
│   └── models.py         # ChatBedrock configuration
└── prompts/
    └── routing_prompts.py # Classification prompt and categories
```

## Future Enhancements

- **Learning from corrections**: Track misclassifications and improve
- **Multi-category routing**: Route to multiple agents in sequence
- **Confidence calibration**: Tune thresholds based on production data
- **Custom categories**: Allow users to define new routing categories

## License

Part of the AI Agent Learning Series on AWS.
