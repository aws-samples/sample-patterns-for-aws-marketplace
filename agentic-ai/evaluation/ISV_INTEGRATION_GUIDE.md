# ISV Integration Guide

This guide explains how to use the ISV partner integrations (Patronus AI, Deepchecks, Comet ML) with the Module 3 evaluation system.

## Overview

Module 3 includes integrations with three ISV partners for advanced evaluation capabilities:

1. **Patronus AI** - Custom evaluation criteria and regression tracking
2. **Deepchecks** - Hallucination detection and LLM output validation
3. **Comet ML** - Experiment tracking and metric logging

## Selective Mock Mode

Each ISV integration operates **independently** with its own mock mode logic:

- If an API key is **present** → Uses **real API** calls
- If an API key is **missing** → Uses **mock mode** (synthetic data)
- If the SDK package is **not installed** → Falls back to **mock mode**

This means you can:
- Use Patronus in real mode while Deepchecks and Comet ML are in mock mode
- Mix and match based on which services you have access to
- Test the system without any API keys (all in mock mode)

## Setup Instructions

### 1. Install Dependencies

The ISV packages are now included in `requirements.txt`:

```bash
pip install -r requirements.txt
```

This will install:
- `patronus>=0.1.0`
- `deepchecks>=0.18.0`
- `comet-ml>=3.35.0`

### 2. Configure API Keys

Set environment variables for the services you want to use:

```bash
# Patronus AI
export PATRONUS_API_KEY="your-patronus-api-key"

# Deepchecks (Note: May not have a free tier)
export DEEPCHECKS_API_KEY="your-deepchecks-api-key"

# Comet ML
export COMET_API_KEY="your-comet-api-key"
```

Or create a `.env` file:

```bash
# .env
PATRONUS_API_KEY=your-patronus-api-key
DEEPCHECKS_API_KEY=your-deepchecks-api-key
COMET_API_KEY=your-comet-api-key
```

### 3. Run the Demo

```bash
# With API keys configured (real mode for those services)
python demos/module3_demo.py

# Without API keys (all in mock mode)
AGENT_MOCK_REPO=true python demos/module3_demo.py
```

## How It Works

### Patronus AI Integration

**Real Mode** (when `PATRONUS_API_KEY` is set):
```python
from evaluation.integrations.patronus_integration import PatronusEvaluator

evaluator = PatronusEvaluator()
# Output: [Patronus] Running in REAL mode with API key

result = evaluator.evaluate(
    task="Generate CDK stack",
    output=cdk_code,
    criteria={"quality": "High quality code"},
)
# Calls real Patronus API
```

**Mock Mode** (when `PATRONUS_API_KEY` is not set):
```python
evaluator = PatronusEvaluator()
# Output: [Patronus] Running in MOCK mode (PATRONUS_API_KEY not set)

result = evaluator.evaluate(...)
# Returns synthetic evaluation data
```

### Deepchecks Integration

**Real Mode** (when `DEEPCHECKS_API_KEY` is set):
```python
from evaluation.integrations.deepchecks_integration import DeepchecksEvaluator

evaluator = DeepchecksEvaluator()
# Output: [Deepchecks] Running in REAL mode with API key

result = evaluator.detect_hallucinations(
    output="Sample output",
    context="Generate CDK",
)
# Calls real Deepchecks API
```

**Mock Mode** (when `DEEPCHECKS_API_KEY` is not set):
```python
evaluator = DeepchecksEvaluator()
# Output: [Deepchecks] Running in MOCK mode (DEEPCHECKS_API_KEY not set)
# Output: [Deepchecks] Note: Deepchecks may not have a free tier available

result = evaluator.detect_hallucinations(...)
# Returns synthetic hallucination detection data
```

### Comet ML Integration

**Real Mode** (when `COMET_API_KEY` is set):
```python
from evaluation.integrations.cometml_integration import CometMLTracker

tracker = CometMLTracker()
# Output: [Comet ML] Running in REAL mode with API key

experiment_id = tracker.start_experiment("eval-run-1")
# Creates real Comet ML experiment
```

**Mock Mode** (when `COMET_API_KEY` is not set):
```python
tracker = CometMLTracker()
# Output: [Comet ML] Running in MOCK mode (COMET_API_KEY not set)

experiment_id = tracker.start_experiment("eval-run-1")
# Returns mock experiment ID
```

## Obtaining API Keys

### Patronus AI - Detailed Setup Guide

**Important**: Patronus requires you to create evaluators in your account before using them via the API. This is a multi-step process.

#### Step 1: Create a Patronus Account

1. Visit [https://app.patronus.ai/signup](https://app.patronus.ai/signup)
2. Sign up with your email and create an account
3. Complete email verification
4. Log in to the Patronus dashboard

#### Step 2: Create Evaluators

Patronus supports several types of evaluators. For this demo, we'll create **custom LLM-based evaluators** that match our evaluation criteria.

**Navigate to Evaluators:**
1. In the Patronus dashboard, click **"Evaluators"** in the left sidebar
2. Click **"Create Evaluator"** button (top right)

**Choose Evaluator Type:**

Patronus offers these evaluator types:
- **Judge** - LLM-based evaluation with custom criteria (recommended for this demo)
- **Classifier** - Binary or multi-class classification
- **Retrieval** - RAG/retrieval quality evaluation
- **Custom** - Python-based custom evaluators

**For this demo, select "Judge" evaluator type.**

#### Step 3: Configure Judge Evaluators

Create **4 separate Judge evaluators** to match our demo criteria:

**Evaluator 1: Completeness**
```yaml
Name: completeness
Display Name: Completeness Evaluator
Type: Judge
Criteria: |
  Evaluate if the CDK code includes all necessary components:
  - All required AWS resources mentioned in requirements
  - Proper imports and dependencies
  - Complete stack initialization
  - No missing or placeholder code
  
Scoring:
  - Scale: 0-100
  - Pass Threshold: 70
  
Evaluation Prompt: |
  You are evaluating AWS CDK infrastructure code for completeness.
  
  Task: {task_input}
  Generated Code: {task_output}
  
  Score the code from 0-100 based on:
  1. All required resources are present (40 points)
  2. Proper imports and setup (20 points)
  3. Complete implementation (no TODOs or placeholders) (20 points)
  4. All parameters properly configured (20 points)
  
  Return only a JSON object: {"score": <0-100>, "explanation": "<brief explanation>"}
```

**Evaluator 2: Accuracy**
```yaml
Name: accuracy
Display Name: Technical Accuracy Evaluator
Type: Judge
Criteria: |
  Evaluate technical correctness of the CDK code:
  - Correct AWS CDK syntax and patterns
  - Proper use of constructs and APIs
  - Valid configuration values
  - Follows AWS best practices
  
Scoring:
  - Scale: 0-100
  - Pass Threshold: 70
  
Evaluation Prompt: |
  You are evaluating AWS CDK code for technical accuracy.
  
  Task: {task_input}
  Generated Code: {task_output}
  
  Score the code from 0-100 based on:
  1. Correct CDK syntax (30 points)
  2. Proper construct usage (30 points)
  3. Valid AWS configurations (20 points)
  4. Best practices followed (20 points)
  
  Return only a JSON object: {"score": <0-100>, "explanation": "<brief explanation>"}
```

**Evaluator 3: Actionability**
```yaml
Name: actionability
Display Name: Actionability Evaluator
Type: Judge
Criteria: |
  Evaluate if the code is ready to deploy:
  - Can be deployed without modifications
  - Clear deployment instructions
  - Proper resource naming
  - Environment configuration present
  
Scoring:
  - Scale: 0-100
  - Pass Threshold: 70
  
Evaluation Prompt: |
  You are evaluating AWS CDK code for actionability (deployment readiness).
  
  Task: {task_input}
  Generated Code: {task_output}
  
  Score the code from 0-100 based on:
  1. Can deploy without changes (40 points)
  2. Clear resource naming (20 points)
  3. Environment variables configured (20 points)
  4. Dependencies specified (20 points)
  
  Return only a JSON object: {"score": <0-100>, "explanation": "<brief explanation>"}
```

**Evaluator 4: Safety Awareness**
```yaml
Name: safety_awareness
Display Name: Security & Safety Evaluator
Type: Judge
Criteria: |
  Evaluate security and safety considerations:
  - Encryption enabled where appropriate
  - Secure defaults used
  - No hardcoded secrets
  - Proper IAM/security groups
  
Scoring:
  - Scale: 0-100
  - Pass Threshold: 70
  
Evaluation Prompt: |
  You are evaluating AWS CDK code for security and safety.
  
  Task: {task_input}
  Generated Code: {task_output}
  
  Score the code from 0-100 based on:
  1. Encryption enabled (30 points)
  2. Secure defaults (30 points)
  3. No hardcoded credentials (20 points)
  4. Proper security configurations (20 points)
  
  Return only a JSON object: {"score": <0-100>, "explanation": "<brief explanation>"}
```

#### Step 4: Save and Note Evaluator IDs

After creating each evaluator:
1. Click **"Save"** or **"Create"**
2. **Copy the Evaluator ID** (usually shown in the URL or evaluator details)
   - Format: `evaluator_<random-string>` or similar
3. Keep these IDs - you'll need them for the code

**Example Evaluator IDs:**
```
completeness: evaluator_abc123def456
accuracy: evaluator_ghi789jkl012
actionability: evaluator_mno345pqr678
safety_awareness: evaluator_stu901vwx234
```

#### Step 5: Get API Key

1. Click your profile icon (top right)
2. Select **"API Keys"** or **"Settings"**
3. Click **"Generate New API Key"**
4. **Copy the API key** (starts with `sk-...`)
5. Store it securely - you won't be able to see it again

#### Step 6: Configure Environment

```bash
export PATRONUS_API_KEY="sk-your-actual-api-key-here"
```

#### Step 7: Update Integration Code

Edit `evaluation/integrations/patronus_integration.py` around line 117:

**Replace this:**
```python
evaluators = []
for criterion_name, criterion_desc in criteria.items():
    evaluators.append(criterion_name)
```

**With your actual evaluator IDs:**
```python
# Map criterion names to your Patronus evaluator IDs
EVALUATOR_ID_MAP = {
    "completeness": "evaluator_abc123def456",
    "accuracy": "evaluator_ghi789jkl012",
    "actionability": "evaluator_mno345pqr678",
    "safety_awareness": "evaluator_stu901vwx234",
}

evaluators = []
for criterion_name in criteria.keys():
    if criterion_name in EVALUATOR_ID_MAP:
        evaluators.append(EVALUATOR_ID_MAP[criterion_name])
    else:
        print(f"  [Patronus] WARNING: No evaluator ID for criterion '{criterion_name}'")
```

#### Step 8: Test the Integration

```bash
export PATRONUS_API_KEY="sk-your-key"
./bin/python demos/module3_demo.py --section 7
```

Expected output:
```
[Patronus] Running in REAL mode with API key
[Patronus] NOTE: Patronus requires pre-configured evaluators in your account
[Patronus] Visit https://app.patronus.ai to create evaluators first
[Patronus] Attempting to use generic evaluators...
[Patronus] ✓ Successfully called Patronus API
Evaluation Results:
  Evaluation ID: eval_xyz789
  Overall Score: 85.5/100
  Pass: True
  Dashboard: https://app.patronus.ai/projects/devops-companion/evaluations
```

#### Troubleshooting

**Error: "Remote evaluator 'X' not found"**
- The evaluator ID doesn't exist in your account
- Double-check the evaluator ID in the Patronus UI
- Ensure you're using the ID, not the name

**Error: "Authentication failed"**
- API key is invalid or expired
- Generate a new API key in Patronus settings
- Ensure `PATRONUS_API_KEY` environment variable is set correctly

**Error: "Failed to get API client"**
- The library wasn't initialized
- This should be fixed in the code, but if you see it, ensure `patronus.init()` is called

#### Alternative: Use Built-in Patronus Evaluators

If Patronus provides built-in evaluators, you can use those instead:

1. In the Patronus UI, go to **"Evaluators"**
2. Look for **"Built-in"** or **"System"** evaluators
3. Common built-in evaluators might include:
   - `judge-consistency`
   - `judge-relevance`
   - `judge-coherence`
   - `hallucination-detector`

4. Use these IDs directly:
```python
evaluators = ["judge-consistency", "judge-relevance", "judge-coherence"]
```

**Note**: Built-in evaluator availability depends on your Patronus plan and account type.

### Deepchecks

**Note**: Deepchecks may not offer a free tier for their LLM testing features.

1. Visit [https://www.deepchecks.com/](https://www.deepchecks.com/)
2. Contact sales for enterprise access
3. If you have access, obtain API key from dashboard
4. Set `DEEPCHECKS_API_KEY` environment variable

**Alternative**: Use mock mode if you don't have access to Deepchecks

### Comet ML

1. Visit [https://www.comet.com/](https://www.comet.com/)
2. Sign up for a free account
3. Navigate to Settings → API Keys
4. Copy your API key
5. Set `COMET_API_KEY` environment variable

## Mock Mode Behavior

### What Mock Mode Does

Mock mode provides **realistic synthetic data** for demonstration and testing:

- **Patronus**: Returns scores based on output length and hash
- **Deepchecks**: Simulates hallucination detection with pattern matching
- **Comet ML**: Creates in-memory experiment tracking

### What Mock Mode Does NOT Do

- ❌ Make real API calls
- ❌ Consume API credits
- ❌ Store data in external platforms
- ❌ Provide actual AI-powered evaluation

### When to Use Mock Mode

- **Development**: Testing the evaluation pipeline without API costs
- **Demos**: Showing the system workflow without credentials
- **CI/CD**: Running tests without external dependencies
- **Limited Access**: When you don't have access to all ISV services

### When to Use Real Mode

- **Production**: Actual agent evaluation and monitoring
- **Quality Assurance**: Validating agent outputs with real AI evaluation
- **Regression Testing**: Tracking agent performance across versions
- **Compliance**: Meeting evaluation requirements with third-party validation

## Troubleshooting

### Package Not Installed

If you see:
```
[Patronus] WARNING: patronus package not installed, falling back to mock mode
```

**Solution**: Install the package:
```bash
pip install patronus
```

### API Key Invalid

If you see:
```
[Patronus] ERROR calling API: Invalid API key
[Patronus] Falling back to mock mode
```

**Solution**: Check your API key is correct and has proper permissions

### Import Errors

If you see import errors for ISV packages:

**Solution**: Reinstall dependencies:
```bash
pip install -r requirements.txt --force-reinstall
```

## Example: Mixed Mode Usage

You can use different modes for different services:

```bash
# Only Comet ML in real mode
export COMET_API_KEY="your-key"
# Patronus and Deepchecks will use mock mode

python demos/module3_demo.py
```

Output:
```
[Patronus] Running in MOCK mode (PATRONUS_API_KEY not set)
[Deepchecks] Running in MOCK mode (DEEPCHECKS_API_KEY not set)
[Comet ML] Running in REAL mode with API key
```

## Best Practices

1. **Start with Mock Mode**: Test the evaluation pipeline before using real APIs
2. **Gradual Rollout**: Enable one ISV at a time to verify integration
3. **Monitor Costs**: Track API usage when using real mode
4. **Fallback Strategy**: Code automatically falls back to mock mode on errors
5. **Environment Variables**: Use `.env` file for local development, secrets manager for production

## Support

For issues with:
- **Patronus AI**: Contact support@patronus.ai
- **Deepchecks**: Contact support@deepchecks.com
- **Comet ML**: Contact support@comet.com
- **This Integration**: Open an issue in the repository
