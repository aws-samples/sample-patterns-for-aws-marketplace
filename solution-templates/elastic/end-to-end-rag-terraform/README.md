# Building a Production RAG Pipeline on AWS in a Day

> An end-to-end Retrieval-Augmented Generation system using Amazon Bedrock, Elastic Cloud, and Terraform — plus the bugs I found (and fixed) in the official AWS template.

This is a working guide. I built this on a Saturday using an [AWS Marketplace sample template](https://github.com/aws-samples/sample-patterns-for-aws-marketplace), ran into four real bugs, fixed them, and submitted a PR back to the repo. Everything here reflects what actually happened, not what the docs said would happen.

---

## Table of Contents

- [What Is RAG, Actually?](#what-is-rag-actually)
- [What Does Terraform Do Here?](#what-does-terraform-do-here)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Step-by-Step Setup](#step-by-step-setup)
- [Bugs in the Official Template (and How to Fix Them)](#bugs-in-the-official-template-and-how-to-fix-them)
- [Testing It End-to-End](#testing-it-end-to-end)
- [Key Things I Learned](#key-things-i-learned)
- [Cost Warning](#cost-warning)
- [Contributing Back](#contributing-back)

---

## What Is RAG, Actually?

RAG stands for Retrieval-Augmented Generation. The idea is simple: instead of asking an LLM to answer questions from memory alone, you give it relevant context pulled from your own documents first.

Here's the mental model that clicked for me:

- **S3** is the filing cabinet — your raw documents live here
- **Elastic** is the memory — it stores searchable vector representations of those documents
- **Bedrock** is the brain — it understands language, turns text into vectors, and generates answers

The pipeline has two phases:

**Ingestion (documents go in):**
```
S3 upload → Lambda Vectorizer → Bedrock Titan Embeddings → Elastic (vector index)
```

**Query (questions come in):**
```
User query → Bedrock Titan Embeddings → Elastic similarity search → Top-k chunks → Bedrock Nova Pro LLM → Answer
```

The key insight is the difference between keyword search and vector search. Keyword search matches the exact words you type. Vector search matches *meaning*. If your document says "vehicle" and you search for "car," a keyword search misses it. A vector search finds it, because the embedding model places semantically similar concepts close together in vector space.

---

## What Does Terraform Do Here?

If you haven't used Terraform before, here's the analogy that made it click:

- **AWS** is the city — it owns the land, enforces the building codes, and sends the bill
- **Terraform** is the architect and construction crew — it picks the land (AWS region), lays the foundation (VPC and networking), puts up the walls (Lambda functions, S3 bucket, API Gateway), and connects the plumbing (PrivateLink tunnel to Elastic)
- **Docker** is the interior — the furniture, the people, and the actual work happening inside the building

Terraform's four commands you'll use:

| Command | What it does |
|---|---|
| `terraform init` | Downloads providers and modules (like `npm install`) |
| `terraform plan` | Dry run — shows exactly what will be created or changed |
| `terraform apply` | Actually builds the infrastructure |
| `terraform destroy` | Tears everything down |

Your `terraform.tfvars` file is your personal configuration. It never goes in Git.

---

## Architecture

```
                         INGESTION PIPELINE
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│   S3 Bucket          Lambda              Amazon Bedrock          │
│  (documents)  ──►  Vectorizer   ──►   Titan Embeddings          │
│                   (chunks text)       (text → vectors)           │
│                                              │                   │
│                                              ▼                   │
│                                    Elastic Cloud (index)         │
│                                    via PrivateLink               │
└──────────────────────────────────────────────────────────────────┘

                          QUERY PIPELINE
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│   HTTP Request       API Gateway        Lambda Agent             │
│   (user query)  ──►  (endpoint)   ──►  (orchestrates)           │
│                                              │                   │
│                          ┌───────────────────┤                   │
│                          ▼                   ▼                   │
│                   Amazon Bedrock      Elastic Cloud              │
│                   Titan Embeddings    similarity_search(k=3)     │
│                   (query → vector)    (find relevant chunks)     │
│                          │                   │                   │
│                          └───────────────────┘                   │
│                                    │                             │
│                                    ▼                             │
│                           Amazon Bedrock                         │
│                           Nova Pro LLM                           │
│                           (generates answer from chunks)         │
│                                    │                             │
│                                    ▼                             │
│                             JSON response                        │
└──────────────────────────────────────────────────────────────────┘

                       AWS NETWORK TOPOLOGY
┌──────────────────────────────────────────────────────────────────┐
│  VPC (10.0.0.0/16)                                               │
│                                                                  │
│  Public Subnets (NAT Gateways)   Private Subnets (Lambdas)       │
│  10.0.40-60.0/24                 10.0.10-30.0/24                 │
│                                         │                        │
│                                         ▼                        │
│                                  VPC Endpoint                    │
│                                  (PrivateLink)                   │
│                                         │                        │
│                                         ▼                        │
│                                  Elastic Cloud                   │
│                                  (external, on AWS)              │
└──────────────────────────────────────────────────────────────────┘
```

### Components

| Component | Service | Role |
|---|---|---|
| Document store | Amazon S3 | Raw documents uploaded here trigger the pipeline |
| Vectorizer | AWS Lambda + Docker | Chunks documents, calls Bedrock for embeddings, writes to Elastic |
| Embeddings | Amazon Bedrock (Titan Embed v1) | Converts text to 1536-dimension vectors |
| Vector store | Elastic Cloud on AWS | Stores and searches vectors via PrivateLink |
| Agent | AWS Lambda + Docker | Receives queries, orchestrates search + generation |
| LLM | Amazon Bedrock (Nova Pro v1) | Generates final answers from retrieved context |
| API | Amazon API Gateway (HTTP) | Public HTTPS endpoint for the agent Lambda |
| Networking | VPC + PrivateLink + NAT | Secure private connectivity to Elastic |
| IaC | Terraform | Everything above, declared as code |

---

## Prerequisites

- An AWS account
- Terraform >= 1.14.7 — install with `brew install hashicorp/tap/terraform`
- AWS CLI v2 — install from [aws.amazon.com/cli](https://aws.amazon.com/cli/)
- Docker Desktop (running)
- Git

---

## Step-by-Step Setup

### 1. Authenticate with AWS

```bash
aws configure
# Enter your Access Key ID, Secret Access Key, and set region to us-east-1
```

Verify it worked:

```bash
aws sts get-caller-identity
```

You should see your account ID and user ARN. If you get an error, your credentials aren't set up correctly — stop here and fix it.

### 2. Enable Amazon Bedrock Models

As of early 2026, Bedrock models are enabled by default in new accounts. You can verify in the AWS Console under **Amazon Bedrock → Model access**. You need:

- `amazon.titan-embed-text-v1` (embeddings)
- `amazon.nova-pro-v1:0` (generation)

If either shows as not enabled, click **Manage model access** and enable them.

### 3. Start an Elastic Cloud Trial on AWS Marketplace

This step is specific: start the trial through **AWS Marketplace**, not through elastic.co directly. The PrivateLink connectivity only works when Elastic is provisioned through Marketplace.

1. Go to [AWS Marketplace](https://aws.amazon.com/marketplace) and search for "Elastic Cloud"
2. Subscribe and start a free trial
3. When creating a deployment, choose:
   - Product: **Elasticsearch**
   - Type: **Hosted**
   - Region: **us-east-1**
4. Once the deployment is running, save:
   - The **Elasticsearch endpoint URL** (looks like `https://HASH.us-east-1.aws.elastic.cloud`)
   - Create an **API key** (from the deployment → Security tab)
   - Note your **deployment ID** from the URL: `cloud.elastic.co/deployments/YOUR_DEPLOYMENT_ID`

### 4. Clone the Repository

```bash
git clone https://github.com/aws-samples/sample-patterns-for-aws-marketplace.git
cd sample-patterns-for-aws-marketplace/solution-templates/elastic/end-to-end-rag-terraform/
```

**Before running any Terraform commands, read the bugs section below.** There are four issues in the original template that will block you. The fixes are straightforward, but you need to apply them before `terraform init` will succeed.

### 5. Store Your Elastic Credentials in AWS Secrets Manager

Never put credentials in code files. They end up in Git history and you'll have a bad day. Store them in Secrets Manager and the Lambda functions fetch them at runtime.

```bash
aws secretsmanager create-secret \
  --name "rag-elastic-credentials" \
  --region us-east-1 \
  --secret-string '{"username":"elastic","password":"YOUR_ELASTIC_PASSWORD"}'
```

The secret costs about $0.40/month. Worth it.

### 6. Create Your terraform.tfvars

Create a file called `terraform.tfvars` in the `end-to-end-rag-terraform/` directory:

```hcl
deployment_id                   = "YOUR_DEPLOYMENT_ID_FROM_CLOUD_ELASTIC_CO"
elasticsearch_connection_secret = "rag-elastic-credentials"
elastic_cloud_api_key           = "YOUR_ELASTIC_CLOUD_API_KEY"
```

The `deployment_id` is the UUID in your Elastic Cloud URL. The `elastic_cloud_api_key` comes from cloud.elastic.co → your profile icon → API Keys → Create API key.

Do not commit this file to Git. Add it to `.gitignore`:

```bash
echo "terraform.tfvars" >> .gitignore
```

### 7. Build and Push Your Docker Images

The original template references Docker images in AWS's internal ECR account (`703671915761`). Cross-account access isn't configured, so your Lambda functions can't pull them. You need to build the images yourself and push them to your own ECR.

**Create your ECR repositories:**

```bash
aws ecr create-repository --repository-name lambda-vectorizer --region us-east-1
aws ecr create-repository --repository-name lambda-agent --region us-east-1
```

**Authenticate Docker to ECR:**

```bash
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
```

**Build and push the vectorizer:**

```bash
cd lambda-vectorizer/src/

docker build \
  --platform linux/amd64 \
  --provenance=false \
  -t YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/lambda-vectorizer:v1.0 .

docker push YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/lambda-vectorizer:v1.0
```

**Build and push the agent:**

```bash
cd ../../lambda-agent/src/

docker build \
  --platform linux/amd64 \
  --provenance=false \
  -t YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/lambda-agent:v1.0 .

docker push YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/lambda-agent:v1.0
```

Two important flags here:

- `--platform linux/amd64`: Lambda runs on x86-64. If you're on an Apple Silicon Mac, Docker defaults to ARM. This flag forces the right architecture.
- `--provenance=false`: When using Docker's `buildx` builder, it creates multi-architecture manifests by default. Lambda doesn't understand that manifest format and rejects the image. This flag disables it.

**Update the function.tf files** in `lambda-vectorizer/` and `lambda-agent/` to point at your ECR URI instead of the original `703671915761` account.

### 8. Deploy with Terraform

```bash
cd ../../  # back to end-to-end-rag-terraform/

terraform init
terraform plan
terraform apply
```

`terraform apply` will prompt you to confirm. Type `yes`.

The full deploy takes roughly 10-15 minutes. At the end, Terraform will output your API Gateway invoke URL — save it.

---

## Bugs in the Official Template (and How to Fix Them)

I found four bugs in the AWS sample template. Three blocked the deployment entirely. One caused runtime failures after the infrastructure came up.

### Bug 1: AWS Provider Version Pin Conflict

**Files:** `private-link/providers.tf` and `data-source/providers.tf`

The original files pin the AWS provider to an exact version:

```hcl
# Original (broken)
aws = {
  source  = "hashicorp/aws"
  version = "6.0.0"
}
```

The VPC module used in `solution.tf` requires `>= 6.28.0`. An exact pin of `6.0.0` satisfies neither constraint — Terraform can't find a version that meets both requirements simultaneously, and `terraform init` fails with a dependency conflict.

**Fix:** Change the exact pin to a minimum version constraint in both files:

```hcl
# Fixed
aws = {
  source  = "hashicorp/aws"
  version = ">= 6.0.0"
}
```

This allows Terraform to select AWS provider `6.37.0` (or whatever current version is available), which satisfies both the `>= 6.0.0` constraint in the submodules and the `>= 6.28.0` requirement of the VPC module.

**PR:** [aws-samples/sample-patterns-for-aws-marketplace#43](https://github.com/aws-samples/sample-patterns-for-aws-marketplace/pull/43)

---

### Bug 2: Wrong Availability Zone for Elastic PrivateLink

**File:** `solution.tf`, line 19

The original template creates the VPC across `us-east-1a`, `us-east-1b`, and `us-east-1c`. The problem is that Elastic's PrivateLink endpoint service doesn't operate in `us-east-1a` — the VPC endpoint can't be created there, and the deployment fails.

You can verify this yourself:

```bash
aws ec2 describe-vpc-endpoint-services \
  --service-names com.amazonaws.vpce.us-east-1.vpce-svc-0e42e1e06ed010238 \
  --query 'ServiceDetails[0].AvailabilityZones'
```

Output:
```json
[
    "us-east-1b",
    "us-east-1c",
    "us-east-1d"
]
```

`us-east-1a` is not in that list.

**Fix:** Update the `azs` in `solution.tf`:

```hcl
# Original (broken)
azs = ["us-east-1a", "us-east-1b", "us-east-1c"]

# Fixed
azs = ["us-east-1b", "us-east-1c", "us-east-1d"]
```

This is a good reminder that AWS services don't always operate in all availability zones within a region. When working with PrivateLink or other regional services, always verify which AZs are actually supported rather than assuming.

**Flagged in PR comment:** [#43 comment](https://github.com/aws-samples/sample-patterns-for-aws-marketplace/pull/43#issuecomment-4103794326)

---

### Bug 3: Pre-built Lambda Images in a Private ECR Account

**All Lambda function definitions**

The template references Docker images hosted in what appears to be AWS's internal ECR account (`703671915761`). Without an explicit resource policy granting cross-account pull access, your Lambda functions fail to start with an image pull error.

This is fixable by building the images yourself from the included Dockerfiles — see Step 7 in the setup section above for the full commands.

After building and pushing to your own ECR, update the `image_uri` in the relevant `function.tf` files within `lambda-vectorizer/` and `lambda-agent/`.

---

### Bug 4: Hardcoded Deprecated Bedrock Model + Body Parsing Error

**File:** `lambda-agent/src/main.py`

The original agent used `amazon.titan-text-premier-v1:0`, which is unavailable, combined with `BedrockLLM` (the older LangChain Bedrock integration):

```python
# Original (broken) — model doesn't exist, wrong class
from langchain_aws import BedrockLLM
llm = BedrockLLM(model_id="amazon.titan-text-premier-v1:0")
```

There was also a body parsing bug — the original code passed the raw JSON string from the API Gateway event body directly to the query function, instead of parsing it first.

**Fix:** Switch to `ChatBedrock` with `amazon.nova-pro-v1:0` and parse the body correctly:

```python
# Fixed
from langchain_aws import ChatBedrock
import json

def get_llm():
    return ChatBedrock(model_id="amazon.nova-pro-v1:0")

def handler(event, context):
    body = event.get("body", "{}")
    if isinstance(body, str):
        body = json.loads(body)   # parse before using
    question = body.get("query", "")
    # ...
```

The `ChatBedrock` class uses the Converse API and is the current recommended way to call Bedrock models through LangChain. The `isinstance` check handles both the API Gateway case (body is a JSON string) and direct Lambda invocation (body is already a dict).

---

## Testing It End-to-End

Once `terraform apply` completes, grab your API Gateway URL from the Terraform outputs:

```bash
terraform output
```

**Upload a document to trigger ingestion:**

```bash
aws s3 cp your-document.txt s3://YOUR_BUCKET_NAME/
```

The S3 event notification triggers the vectorizer Lambda automatically. Give it about 30 seconds to chunk, embed, and index the document.

**Query the RAG:**

```bash
curl -X POST https://YOUR_INVOKE_URL/agent \
  -H "Content-Type: application/json" \
  -d '{"query": "What does this document say about X?"}'
```

You should get back a JSON response with the LLM's answer, grounded in the content of your document.

**Check Lambda logs if something goes wrong:**

```bash
# Vectorizer logs
aws logs tail /aws/lambda/lambda-vectorizer --follow

# Agent logs
aws logs tail /aws/lambda/lambda-agent --follow
```

---

## Key Things I Learned

### Regions vs. Availability Zones

These are different things. A **region** is a geographic area (`us-east-1` = Northern Virginia). An **availability zone** is an individual data center within that region (`us-east-1a`, `us-east-1b`, etc.). Services don't always operate in every AZ within a region — this is exactly what caused Bug 2. Always check before assuming.

### AWS Secrets Manager is Non-Negotiable

Credentials in code files end up in Git history. Secrets Manager costs about $0.40/month per secret and keeps credentials out of your codebase entirely. The Lambda functions in this project fetch the Elastic username and password from Secrets Manager at startup — the actual values never touch the code.

### Docker + Lambda Has Quirks

Lambda supports container images, which is great for packages that are too large for a zip deployment (like this vectorizer, which pulls in `unstructured`, `torch`, and OCR tools). But there are two things you must get right:

1. **Build for `linux/amd64`**, even if you're on an Apple Silicon Mac. Lambda runs on x86-64. Use `--platform linux/amd64`.
2. **Use `--provenance=false`** when building with Docker's `buildx` builder. Without it, buildx creates a multi-architecture manifest that Lambda can't interpret, and your function will fail to start with a cryptic error.

### LangChain Moves Fast

The `BedrockLLM` class is deprecated in favor of `ChatBedrock`. Model IDs change. If you're referencing a model by ID anywhere in code, verify it's still available in the Bedrock console before assuming the code will work.

---

## Cost Warning

This architecture is not cheap to leave running. The main culprits:

| Resource | Hourly rate | Monthly if left on |
|---|---|---|
| 3x NAT Gateways | ~$0.135/hr | ~$97 |
| PrivateLink endpoint | ~$0.010/hr | ~$7 |
| **Total idle cost** | **~$0.145/hr** | **~$104** |

That's before any Lambda invocations or Bedrock API calls.

**Always tear down when you're done:**

```bash
terraform destroy
```

Type `yes` when prompted. The whole stack will be removed in a few minutes. At roughly $3.50/day, forgetting to do this is an expensive mistake.

---

## Contributing Back

After working through these bugs, I submitted [PR #43](https://github.com/aws-samples/sample-patterns-for-aws-marketplace/pull/43) to the official AWS repo with the provider version fix and the AZ correction.

At the time of submission, it was the first PR from a human contributor — every previous PR in the repo had come from an automated bot. If you run into additional issues and fix them, consider submitting a PR. The template is used by people learning this stack, and each improvement makes it easier for the next person.

---

## Project Structure

```
end-to-end-rag-terraform/
├── solution.tf              # Top-level orchestration — VPC, modules wired together
├── variables.tf             # Input variable declarations
├── terraform.tfvars         # Your config (not in Git)
├── outputs.tf               # What Terraform prints after apply
│
├── data-source/             # S3 bucket + event notification to vectorizer Lambda
├── private-link/            # VPC endpoint connecting your VPC to Elastic Cloud
├── api-gateway/             # HTTP API Gateway wired to the agent Lambda
│
├── lambda-vectorizer/       # Ingestion Lambda
│   └── src/
│       ├── main.py          # S3 event handler: load → chunk → embed → index
│       ├── Dockerfile       # Python 3.12 + unstructured + tesseract OCR
│       └── requirements.txt
│
└── lambda-agent/            # Query Lambda
    └── src/
        ├── main.py          # Query handler: embed → search → generate → respond
        ├── Dockerfile       # Python 3.12 + langchain + bedrock
        └── requirements.txt
```

---

*Built on AWS with Terraform, Elastic Cloud, and Amazon Bedrock. Template from [aws-samples/sample-patterns-for-aws-marketplace](https://github.com/aws-samples/sample-patterns-for-aws-marketplace).*
