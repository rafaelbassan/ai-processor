"""Specialists module - specialized agents for specific domains."""

from .nutritionist_agent import nutritionist_agent
from .performance_analyst_agent import performance_analyst_agent
from .running_technique_specialist import running_technique_specialist

__all__ = [
    'nutritionist_agent',
    'performance_analyst_agent',
    'running_technique_specialist',
]
