"""Workflows module - sequential agent workflows."""

from .generic_analysis_workflow import generic_analysis_workflow
from .swimming_analysis_workflow import swimming_analysis_workflow
from .running_analysis_workflow import running_analysis_workflow

__all__ = [
    'generic_analysis_workflow',
    'swimming_analysis_workflow',
    'running_analysis_workflow',
]
