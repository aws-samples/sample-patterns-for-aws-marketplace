"""
evaluation/integrations/cometml_integration.py
===============================================
Comet ML integration for experiment tracking and performance monitoring.

Comet ML provides:
- Experiment tracking
- Model performance monitoring
- Anomaly detection
- Visualization dashboards

Note: This is a mock implementation. Real integration requires Comet ML API key.
"""

from __future__ import annotations

import os
from typing import Any
from datetime import datetime, timezone


class CometMLTracker:
    """
    Comet ML tracker for agent evaluation experiments.
    """
    
    def __init__(
        self,
        api_key: str | None = None,
        project_name: str = "devops-companion-eval",
    ):
        """
        Initialize Comet ML tracker.
        
        Parameters
        ----------
        api_key : str, optional
            Comet ML API key. Falls back to COMET_API_KEY env var.
        project_name : str
            Project name for organizing experiments.
        """
        self.api_key = api_key or os.getenv("COMET_API_KEY")
        self.project_name = project_name
        # Use mock mode only if API key is not provided
        self.mock_mode = not self.api_key
        self.experiments: dict[str, dict] = {}
        
        if self.mock_mode:
            print("  [Comet ML] Running in MOCK mode (COMET_API_KEY not set)")
            self.comet_ml = None
        else:
            print("  [Comet ML] Running in REAL mode with API key")
            # Try to import comet_ml SDK
            try:
                import comet_ml
                self.comet_ml = comet_ml
                # Set API key in environment for Comet ML
                os.environ["COMET_API_KEY"] = self.api_key
            except ImportError:
                print("  [Comet ML] WARNING: comet-ml package not installed, falling back to mock mode")
                self.mock_mode = True
                self.comet_ml = None
            except Exception as e:
                print(f"  [Comet ML] WARNING: Failed to initialize Comet ML: {e}")
                print("  [Comet ML] Falling back to mock mode")
                self.mock_mode = True
                self.comet_ml = None
        
        self.current_experiment = None
    
    def start_experiment(
        self,
        experiment_name: str,
        tags: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> str:
        """
        Start a new experiment.
        
        Parameters
        ----------
        experiment_name : str
            Name for the experiment.
        tags : list of str, optional
            Tags for categorizing the experiment.
        parameters : dict, optional
            Experiment parameters (model config, hyperparameters, etc.).
        
        Returns
        -------
        str
            Experiment ID.
        """
        if self.mock_mode:
            return self._mock_start_experiment(experiment_name, tags, parameters)
        
        # Real Comet ML integration
        try:
            experiment = self.comet_ml.Experiment(
                api_key=self.api_key,
                project_name=self.project_name,
            )
            experiment.set_name(experiment_name)
            if tags:
                experiment.add_tags(tags)
            if parameters:
                experiment.log_parameters(parameters)
            
            experiment_id = experiment.get_key()
            self.experiments[experiment_id] = {
                "experiment": experiment,
                "name": experiment_name,
                "start_time": datetime.now(timezone.utc).isoformat(),
            }
            return experiment_id
        except Exception as e:
            print(f"  [Comet ML] ERROR starting experiment: {e}")
            print("  [Comet ML] Falling back to mock mode")
            return self._mock_start_experiment(experiment_name, tags, parameters)
    
    def _mock_start_experiment(
        self,
        experiment_name: str,
        tags: list[str] | None,
        parameters: dict[str, Any] | None,
    ) -> str:
        """Mock experiment start."""
        experiment_id = f"exp-{hash(experiment_name) % 100000}"
        
        self.current_experiment = {
            "id": experiment_id,
            "name": experiment_name,
            "tags": tags or [],
            "parameters": parameters or {},
            "metrics": {},
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        
        return experiment_id
    
    def log_metrics(
        self,
        metrics: dict[str, float],
        step: int | None = None,
        epoch: int | None = None,
    ) -> None:
        """
        Log metrics for current experiment.
        
        Parameters
        ----------
        metrics : dict
            Metrics to log (e.g., {"accuracy": 0.95, "latency": 1.2}).
        step : int, optional
            Step number.
        epoch : int, optional
            Epoch number.
        """
        if self.mock_mode:
            self._mock_log_metrics(metrics, step, epoch)
            return
        
        # Real Comet ML metric logging would go here
        # self.current_experiment.log_metrics(metrics, step=step, epoch=epoch)
        
        self._mock_log_metrics(metrics, step, epoch)
    
    def _mock_log_metrics(
        self,
        metrics: dict[str, float],
        step: int | None,
        epoch: int | None,
    ) -> None:
        """Mock metric logging."""
        if self.current_experiment:
            for name, value in metrics.items():
                if name not in self.current_experiment["metrics"]:
                    self.current_experiment["metrics"][name] = []
                self.current_experiment["metrics"][name].append({
                    "value": value,
                    "step": step,
                    "epoch": epoch,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
    
    def log_evaluation_results(
        self,
        results: dict[str, Any],
        agent_version: str,
    ) -> None:
        """
        Log evaluation results.
        
        Parameters
        ----------
        results : dict
            Evaluation results from evaluation pipeline.
        agent_version : str
            Agent version identifier.
        """
        summary = results.get("summary", {})
        
        metrics = {
            "average_score": summary.get("average_score", 0),
            "pass_rate": summary.get("pass_rate", 0),
            "min_score": summary.get("min_score", 0),
            "max_score": summary.get("max_score", 0),
        }
        
        # Log criteria scores
        criteria_scores = summary.get("criteria_scores", {})
        for criterion, stats in criteria_scores.items():
            metrics[f"{criterion}_avg"] = stats.get("average", 0)
        
        self.log_metrics(metrics)
        
        # Log parameters
        if self.current_experiment:
            self.current_experiment["parameters"]["agent_version"] = agent_version
            self.current_experiment["parameters"]["total_test_cases"] = summary.get("total_test_cases", 0)
    
    def detect_anomalies(
        self,
        metric_name: str,
        threshold: float = 2.0,
    ) -> dict[str, Any]:
        """
        Detect anomalies in metrics.
        
        Parameters
        ----------
        metric_name : str
            Metric to check for anomalies.
        threshold : float
            Standard deviation threshold for anomaly detection.
        
        Returns
        -------
        dict
            Anomaly detection results.
        """
        if self.mock_mode:
            return self._mock_detect_anomalies(metric_name, threshold)
        
        # Real Comet ML anomaly detection would go here
        return self._mock_detect_anomalies(metric_name, threshold)
    
    def _mock_detect_anomalies(
        self,
        metric_name: str,
        threshold: float,
    ) -> dict[str, Any]:
        """Mock anomaly detection."""
        if not self.current_experiment or metric_name not in self.current_experiment["metrics"]:
            return {
                "anomalies_detected": False,
                "anomaly_count": 0,
                "message": f"No data for metric: {metric_name}",
            }
        
        values = [m["value"] for m in self.current_experiment["metrics"][metric_name]]
        
        if len(values) < 3:
            return {
                "anomalies_detected": False,
                "anomaly_count": 0,
                "message": "Insufficient data for anomaly detection",
            }
        
        # Simple anomaly detection: values far from mean
        mean = sum(values) / len(values)
        std = (sum((x - mean) ** 2 for x in values) / len(values)) ** 0.5
        
        anomalies = []
        for i, value in enumerate(values):
            if abs(value - mean) > threshold * std:
                anomalies.append({
                    "index": i,
                    "value": value,
                    "deviation": abs(value - mean) / std if std > 0 else 0,
                })
        
        return {
            "anomalies_detected": len(anomalies) > 0,
            "anomaly_count": len(anomalies),
            "anomalies": anomalies,
            "mean": mean,
            "std": std,
            "threshold": threshold,
            "mock_mode": True,
        }
    
    def end_experiment(self) -> dict[str, Any]:
        """
        End current experiment and return summary.
        
        Returns
        -------
        dict
            Experiment summary.
        """
        if not self.current_experiment:
            return {"error": "No active experiment"}
        
        self.current_experiment["ended_at"] = datetime.now(timezone.utc).isoformat()
        
        summary = {
            "experiment_id": self.current_experiment["id"],
            "name": self.current_experiment["name"],
            "duration": "calculated in real implementation",
            "metrics_logged": len(self.current_experiment["metrics"]),
            "dashboard_url": f"https://www.comet.ml/{self.workspace}/{self.project_name}/{self.current_experiment['id']}",
            "mock_mode": self.mock_mode,
        }
        
        experiment = self.current_experiment
        self.current_experiment = None
        
        return summary
