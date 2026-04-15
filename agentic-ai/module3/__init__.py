"""
module3
=======
Module 3: Agent Evaluation and CDK Infrastructure Generation.

This module implements:
- CDK infrastructure generation agent using LangChain
- Evaluation harnesses for Module 2 and Module 3
- Integration with ISV partners (Patronus AI, Deepchecks, Comet ML)
- LLM-as-judge evaluation pattern
- Self-correction pattern

The agent receives infrastructure requirements (from Module 2 repository analysis)
and generates production-ready AWS CDK stacks with best practices.
"""

__version__ = "0.1.0"
