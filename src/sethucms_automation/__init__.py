"""Automation workflows that pull data from websites, check it, and land it in SethuCMS.

The pipeline has five steps, and only the last one writes anything:

    fetch a page  ->  extract fields (AI step)  ->  validate  ->  land in SethuCMS
                                                      |
                                       rejected records are reported, never written
"""
from .models import FieldSpec, RunReport
from .workflow import Workflow

__all__ = ["FieldSpec", "RunReport", "Workflow"]
