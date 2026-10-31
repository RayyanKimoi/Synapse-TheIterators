"""Loads reference workflow IR documents from the workflows/ directory."""

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .config import get_settings
from .models.ir import WorkflowIR


class WorkflowSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    name: str
    node_count: int
    source_file: str


@lru_cache
def _loaded() -> dict[str, tuple[WorkflowIR, str]]:
    directory: Path = get_settings().workflows_dir
    workflows: dict[str, tuple[WorkflowIR, str]] = {}
    for path in sorted(directory.glob("*.json")):
        workflow = WorkflowIR.model_validate(json.loads(path.read_text(encoding="utf-8")))
        workflows[workflow.workflow_id] = (workflow, path.name)
    return workflows


def get(workflow_id: str) -> WorkflowIR | None:
    entry = _loaded().get(workflow_id)
    return entry[0] if entry else None


def summaries() -> list[WorkflowSummary]:
    return [
        WorkflowSummary(
            workflow_id=workflow.workflow_id,
            name=workflow.name,
            node_count=len(workflow.nodes),
            source_file=filename,
        )
        for workflow, filename in _loaded().values()
    ]
