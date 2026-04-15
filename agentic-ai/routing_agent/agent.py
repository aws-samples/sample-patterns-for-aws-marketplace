"""
routing-agent/agent.py
======================
Intent classification agent for routing requests to specialist agents.

This is a simple single-shot classification agent (not a full ReAct loop).
It uses a single LLM call to classify the intent and return routing information.
"""

from __future__ import annotations

import json
import os
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from routing_agent.config.models import get_chat_bedrock_model
from routing_agent.prompts.routing_prompts import ROUTING_PROMPT, CATEGORY_DESCRIPTIONS


# ---------------------------------------------------------------------------
# Agent URLs Configuration
# ---------------------------------------------------------------------------

AGENT_URLS = {
    "module1": os.getenv("MODULE1_URL", "http://localhost:8080"),
    "module2": os.getenv("MODULE2_URL", "http://localhost:8081"),
    "module3": os.getenv("MODULE3_URL", "http://localhost:8082"),
}


# ---------------------------------------------------------------------------
# Classification Function
# ---------------------------------------------------------------------------

def classify_intent(
    request: str,
    region: str | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Classify the intent of a user request and determine routing.

    This is a single-shot classification (no agent loop needed).
    Uses Claude Sonnet 4 with temperature=0.0 for deterministic classification.

    Parameters
    ----------
    request : str
        User's request text.
    region : str, optional
        AWS region for Bedrock.
    verbose : bool
        Print classification details.

    Returns
    -------
    dict
        Classification result with category, confidence, target agent, and URL.

    Example
    -------
    >>> from routing_agent.agent import classify_intent
    >>> result = classify_intent("Analyze the repository at /home/user/app")
    >>> print(result["category"])  # "repository_analysis"
    >>> print(result["target_agent"])  # "module2"
    >>> print(result["target_url"])  # "http://localhost:8081"
    """
    # Get model with temperature=0.0 for deterministic classification
    model = get_chat_bedrock_model(region=region, temperature=0.0)
    
    # Create prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", ROUTING_PROMPT),
        ("user", "{request}"),
    ])
    
    # Create chain
    chain = prompt | model | StrOutputParser()
    
    # Invoke classification
    if verbose:
        print(f"  [Routing Agent] Classifying request...")
        print(f"  [Request] {request[:100]}...")
    
    response = chain.invoke({"request": request})
    
    # Parse JSON response
    try:
        # Extract JSON from response (handle markdown code blocks)
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0].strip()
        else:
            json_str = response.strip()
        
        result = json.loads(json_str)
        
        # Add target URL
        target_agent = result.get("target_agent", "unknown")
        result["target_url"] = AGENT_URLS.get(target_agent, "")
        
        if verbose:
            print(f"  [Category] {result['category']}")
            print(f"  [Confidence] {result['confidence']}")
            print(f"  [Target Agent] {target_agent}")
            print(f"  [Target URL] {result['target_url']}")
            if result.get("clarifying_questions"):
                print(f"  [Questions] {len(result['clarifying_questions'])} clarifying questions")
        
        return result
        
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        # Fallback if JSON parsing fails
        if verbose:
            print(f"  [Warning] Failed to parse classification response: {e}")
        
        return {
            "category": "unknown",
            "confidence": 0.0,
            "reasoning": "Failed to parse classification response",
            "clarifying_questions": ["Could you please rephrase your request?"],
            "target_agent": "unknown",
            "target_url": "",
            "raw_response": response,
        }


def route_request(
    request: str,
    region: str | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Classify intent and provide routing information.

    This is a convenience function that wraps classify_intent with
    additional routing metadata.

    Parameters
    ----------
    request : str
        User's request text.
    region : str, optional
        AWS region for Bedrock.
    verbose : bool
        Print routing details.

    Returns
    -------
    dict
        Routing information including category, confidence, target agent/URL,
        and suggested action.

    Example
    -------
    >>> from routing_agent.agent import route_request
    >>> routing = route_request("Generate CDK for a web app")
    >>> print(routing["suggested_action"])
    """
    classification = classify_intent(request, region=region, verbose=verbose)
    
    # Determine suggested action based on confidence
    confidence = classification.get("confidence", 0.0)
    category = classification.get("category", "unknown")
    
    if confidence >= 0.7:
        action = "route"
        message = f"Route to {classification.get('target_agent', 'unknown')}"
    elif confidence >= 0.5:
        action = "clarify"
        message = "Request clarification before routing"
    else:
        action = "reject"
        message = "Unable to classify request"
    
    # Add routing metadata
    routing_info = {
        **classification,
        "suggested_action": action,
        "action_message": message,
        "category_info": CATEGORY_DESCRIPTIONS.get(category, {}),
    }
    
    return routing_info


# ---------------------------------------------------------------------------
# Batch Classification
# ---------------------------------------------------------------------------

def classify_batch(
    requests: list[str],
    region: str | None = None,
    verbose: bool = False,
) -> list[dict[str, Any]]:
    """
    Classify multiple requests in batch.

    Parameters
    ----------
    requests : list of str
        List of user requests to classify.
    region : str, optional
        AWS region for Bedrock.
    verbose : bool
        Print classification details for each request.

    Returns
    -------
    list of dict
        Classification results for each request.

    Example
    -------
    >>> requests = [
    ...     "Analyze my repository",
    ...     "Generate CDK for ECS",
    ...     "Check AWS health",
    ... ]
    >>> results = classify_batch(requests)
    >>> for r in results:
    ...     print(f"{r['category']}: {r['confidence']}")
    """
    results = []
    
    for i, request in enumerate(requests):
        if verbose:
            print(f"\n[Batch {i+1}/{len(requests)}]")
        
        result = classify_intent(request, region=region, verbose=verbose)
        results.append(result)
    
    return results
