"""VectoSports AI agents module."""

from .core import root_agent
from .analysts import generic_analyst_agent, swimming_analyst_agent
from .specialists import nutritionist_agent, performance_analyst_agent
from .reviewers import (
    reviewer_agent,
    reviewer_agent_generic,
    reviewer_agent_swimming,
)
from .workflows import generic_analysis_workflow, swimming_analysis_workflow

__all__ = [
    'root_agent',
    'generic_analyst_agent',
    'swimming_analyst_agent',
    'nutritionist_agent',
    'performance_analyst_agent',
    'reviewer_agent',
    'reviewer_agent_generic',
    'reviewer_agent_swimming',
    'generic_analysis_workflow',
    'swimming_analysis_workflow',
]
