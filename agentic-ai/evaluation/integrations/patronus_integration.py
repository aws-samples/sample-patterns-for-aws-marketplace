"""
evaluation/integrations/patronus_integration.py
================================================
Patronus AI integration for automated evaluation with custom criteria.

Patronus AI provides:
- Custom evaluation criteria definition
- Automated scoring
- Regression tracking across agent versions
- Evaluation dashboard

Note: This is a mock implementation. Real integration requires Patronus API key.
"""

from __future__ import annotations

import os
from typing import Any
from datetime import datetime, timezone


class PatronusEvaluator:
    """
    Patronus AI evaluator for agent outputs.
    
    Provides automated evaluation with custom criteria and regression tracking.
    """
    
    def __init__(self, api_key: str | None = None, project_name: str = "devops-companion"):
        """
        Initialize Patronus evaluator.
        
        Parameters
        ----------
        api_key : str, optional
            Patronus API key. Falls back to PATRONUS_API_KEY env var.
        project_name : str
            Project name for organizing evaluations.
        """
        self.api_key = api_key or os.getenv("PATRONUS_API_KEY")
        self.project_name = project_name
        # Use mock mode only if API key is not provided
        self.mock_mode = not self.api_key
        
        if self.mock_mode:
            print("  [Patronus] Running in MOCK mode (PATRONUS_API_KEY not set)")
            self.client = None
        else:
            print("  [Patronus] Running in REAL mode with API key")
            # Try to import and initialize patronus SDK
            try:
                import patronus
                from patronus import Patronus
                
                # Initialize Patronus library with API key
                patronus.init(api_key=self.api_key)
                
                # Create Patronus client
                self.client = Patronus()
            except ImportError:
                print("  [Patronus] WARNING: patronus package not installed, falling back to mock mode")
                self.mock_mode = True
                self.client = None
            except Exception as e:
                print(f"  [Patronus] WARNING: Failed to initialize Patronus client: {e}")
                print("  [Patronus] Falling back to mock mode")
                self.mock_mode = True
                self.client = None
    
    def evaluate(
        self,
        task: str,
        output: str,
        criteria: dict[str, str],
        reference: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Evaluate agent output using Patronus AI.
        
        Parameters
        ----------
        task : str
            Task description.
        output : str
            Agent's output to evaluate.
        criteria : dict
            Custom evaluation criteria.
        reference : str, optional
            Reference answer.
        metadata : dict, optional
            Additional metadata (agent version, test case ID, etc.).
        
        Returns
        -------
        dict
            Evaluation results with scores and tracking ID.
        """
        if self.mock_mode:
            return self._mock_evaluate(task, output, criteria, reference, metadata)
        
        # Real Patronus API integration
        try:
            # Note: Patronus requires evaluators to be pre-configured in your account
            # You need to create evaluators via the Patronus UI or API first
            # For this demo, we'll attempt to use common evaluator names
            
            # Try to use a generic evaluator if available
            # In production, you would specify actual evaluator IDs from your Patronus account
            print("  [Patronus] NOTE: Patronus requires pre-configured evaluators in your account")
            print("  [Patronus] Visit https://app.patronus.ai to create evaluators first")
            print("  [Patronus] Attempting to use generic evaluators...")
            
            # Build evaluators list - these need to match evaluator IDs in your Patronus account
            # Common built-in evaluators: 'judge-consistency', 'judge-relevance', etc.
            evaluators = []
            for criterion_name, criterion_desc in criteria.items():
                # Try using the criterion name as evaluator ID
                # This will fail if the evaluator doesn't exist in your account
                evaluators.append(criterion_name)
            
            # Call Patronus evaluate
            result = self.client.evaluate(
                evaluators=evaluators,
                task_input=task,
                task_output=output,
                gold_answer=reference,
                task_metadata={
                    "project": self.project_name,
                    **(metadata or {}),
                },
            )
            
            # Extract scores from result
            scores = {}
            overall_score = 0
            if hasattr(result, 'results') and result.results:
                for eval_result in result.results:
                    if hasattr(eval_result, 'evaluator_id') and hasattr(eval_result, 'score'):
                        scores[eval_result.evaluator_id] = eval_result.score
                        overall_score += eval_result.score
                if scores:
                    overall_score = overall_score / len(scores)
            
            print("  [Patronus] ✓ Successfully called Patronus API")
            return {
                "evaluation_id": getattr(result, 'evaluation_id', f"patronus-{hash(output) % 100000}"),
                "project": self.project_name,
                "task": task,
                "scores": scores if scores else {"overall": 0},
                "overall_score": overall_score,
                "pass": overall_score >= 70,
                "metadata": metadata or {},
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "dashboard_url": f"https://app.patronus.ai/projects/{self.project_name}/evaluations",
                "mock_mode": False,
            }
        except Exception as e:
            error_msg = str(e)
            print(f"  [Patronus] ERROR calling API: {e}")
            print(f"  [Patronus] Error type: {type(e).__name__}")
            
            if "not found" in error_msg.lower() or "evaluator" in error_msg.lower():
                print("  [Patronus] ")
                print("  [Patronus] To use Patronus in real mode:")
                print("  [Patronus] 1. Visit https://app.patronus.ai")
                print("  [Patronus] 2. Create evaluators in your account")
                print("  [Patronus] 3. Update this code to use your evaluator IDs")
                print("  [Patronus] ")
            
            print("  [Patronus] Falling back to mock mode")
            return self._mock_evaluate(task, output, criteria, reference, metadata)
    
    def _mock_evaluate(
        self,
        task: str,
        output: str,
        criteria: dict[str, str],
        reference: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Mock evaluation for testing."""
        # Simulate Patronus evaluation
        scores = {}
        for criterion in criteria.keys():
            # Mock score based on output length and criterion
            base_score = min(95, 60 + len(output) // 100)
            scores[criterion] = base_score + hash(criterion) % 20
        
        overall_score = sum(scores.values()) / len(scores) if scores else 0
        
        return {
            "evaluation_id": f"patronus-{hash(output) % 100000}",
            "project": self.project_name,
            "task": task,
            "scores": scores,
            "overall_score": overall_score,
            "pass": overall_score >= 70,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dashboard_url": f"https://app.patronus.ai/projects/{self.project_name}/evaluations",
            "mock_mode": True,
        }
    
    def track_regression(
        self,
        agent_version: str,
        evaluation_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Track regression across agent versions.
        
        Parameters
        ----------
        agent_version : str
            Agent version identifier (e.g., "v1.0.0", "module3-baseline").
        evaluation_results : list of dict
            List of evaluation results from evaluate().
        
        Returns
        -------
        dict
            Regression tracking summary.
        """
        if self.mock_mode:
            return self._mock_track_regression(agent_version, evaluation_results)
        
        # Real Patronus regression tracking would go here
        return self._mock_track_regression(agent_version, evaluation_results)
    
    def _mock_track_regression(
        self,
        agent_version: str,
        evaluation_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Mock regression tracking."""
        scores = [r.get("overall_score", 0) for r in evaluation_results]
        
        return {
            "agent_version": agent_version,
            "total_evaluations": len(evaluation_results),
            "average_score": sum(scores) / len(scores) if scores else 0,
            "pass_rate": sum(1 for s in scores if s >= 70) / len(scores) if scores else 0,
            "regression_detected": False,  # Would compare to previous version
            "dashboard_url": f"https://app.patronus.ai/projects/{self.project_name}/versions/{agent_version}",
            "mock_mode": True,
        }
    
    def create_custom_criteria(
        self,
        name: str,
        description: str,
        scoring_rubric: dict[str, str],
    ) -> dict[str, Any]:
        """
        Create custom evaluation criteria in Patronus.
        
        Parameters
        ----------
        name : str
            Criterion name.
        description : str
            Criterion description.
        scoring_rubric : dict
            Scoring rubric with score ranges and descriptions.
        
        Returns
        -------
        dict
            Created criterion metadata.
        """
        return {
            "criterion_id": f"custom-{hash(name) % 10000}",
            "name": name,
            "description": description,
            "scoring_rubric": scoring_rubric,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mock_mode": self.mock_mode,
        }
