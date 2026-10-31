"""SYNAPSE HTTP surface (PRD sections 5.1 and 11, Phase 1)."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sse_starlette.sse import EventSourceResponse

from .. import registry
from ..compiler.dag import CompileError
from ..compiler.planner import CompilePlan, compile_workflow
from ..config import get_settings
from ..llm.gateway import LLMGateway
from ..models.ir import WorkflowIR
from ..models.telemetry import PipelineType
from ..runtime.mock_runner import stream_telemetry

router = APIRouter(prefix="/api/v1")

# Compressing wall-clock time is a rehearsal aid; 1.0 is the real-time demo path.
TimeScale = Annotated[float, Query(ge=1.0, le=200.0)]


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow: WorkflowIR | None = None
    workflow_id: str | None = None
    mode: PipelineType = PipelineType.COMPILED
    cache_warm: bool = False
    time_scale: float = Field(default=1.0, ge=1.0, le=200.0)

    @model_validator(mode="after")
    def _require_a_workflow(self) -> "ExecuteRequest":
        if (self.workflow is None) == (self.workflow_id is None):
            raise ValueError("provide exactly one of 'workflow' or 'workflow_id'")
        return self


def _resolve(workflow: WorkflowIR | None, workflow_id: str | None) -> WorkflowIR:
    if workflow is not None:
        return workflow
    found = registry.get(workflow_id or "")
    if found is None:
        raise HTTPException(status_code=404, detail=f"unknown workflow_id '{workflow_id}'")
    return found


def _stream(
    workflow: WorkflowIR, mode: PipelineType, cache_warm: bool, time_scale: float
) -> EventSourceResponse:
    settings = get_settings()
    return EventSourceResponse(
        stream_telemetry(
            workflow,
            mode=mode,
            cache_warm=cache_warm,
            tick_ms=settings.telemetry_tick_ms,
            time_scale=time_scale,
        ),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/health")
async def health() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "ok",
        "environment": settings.environment,
        "llm": await LLMGateway(settings).probe(),
        "workflows_loaded": len(registry.summaries()),
    }


@router.get("/workflows", response_model=list[registry.WorkflowSummary])
async def list_workflows() -> list[registry.WorkflowSummary]:
    return registry.summaries()


@router.get("/workflows/{workflow_id}", response_model=WorkflowIR)
async def get_workflow(workflow_id: str) -> WorkflowIR:
    return _resolve(None, workflow_id)


@router.post("/compile", response_model=CompilePlan)
async def compile_endpoint(workflow: WorkflowIR) -> CompilePlan:
    """Validate the IR, reject cycles, and return the tiered execution plan."""
    try:
        return compile_workflow(workflow)
    except CompileError as exc:
        raise HTTPException(
            status_code=400, detail={"message": exc.message, "cycle": exc.cycle}
        ) from exc


@router.post("/execute/stream")
async def execute_stream(request: ExecuteRequest) -> EventSourceResponse:
    workflow = _resolve(request.workflow, request.workflow_id)
    return _stream(workflow, request.mode, request.cache_warm, request.time_scale)


@router.get("/execute/stream")
async def execute_stream_get(
    workflow_id: str,
    mode: PipelineType = PipelineType.COMPILED,
    cache_warm: bool = False,
    time_scale: TimeScale = 1.0,
) -> EventSourceResponse:
    """GET variant so the browser's native EventSource can subscribe directly."""
    return _stream(_resolve(None, workflow_id), mode, cache_warm, time_scale)
