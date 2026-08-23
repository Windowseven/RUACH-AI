from fastapi import APIRouter, Depends

from app.api.dependencies import get_tool_engine
from app.api.middleware import request_id_var
from app.api.schemas.tools import (
    CapabilityInfo,
    ToolCallIn,
    ToolOutcomeOut,
    ToolOutcomeResponse,
    ToolRegistryData,
    ToolRegistryResponse,
)
from app.application.tools.engine import ToolEngine
from app.application.tools.policy import CAPABILITY_RISK
from app.application.tools.schemas import RiskLevel, ToolOutcome, ToolRequest

router = APIRouter(prefix="/tools", tags=["tools"])


def _outcome_response(outcome: ToolOutcome) -> ToolOutcomeResponse:
    return ToolOutcomeResponse(
        data=ToolOutcomeOut(
            state=outcome.state,
            output=outcome.output,
            reason=outcome.reason,
            approval_id=outcome.approval_id,
        ),
        request_id=request_id_var.get(),
    )


@router.get("", response_model=ToolRegistryResponse)
def registry() -> ToolRegistryResponse:
    tools = [
        CapabilityInfo(
            capability=capability,
            risk_level=int(risk),
            approval_required=risk >= RiskLevel.DESTRUCTIVE,
        )
        for capability, risk in sorted(CAPABILITY_RISK.items())
    ]
    return ToolRegistryResponse(
        data=ToolRegistryData(tools=tools, mode="restricted"),
        request_id=request_id_var.get(),
    )


@router.post("/requests", response_model=ToolOutcomeResponse)
def submit_tool_request(
    payload: ToolCallIn,
    engine: ToolEngine = Depends(get_tool_engine),
) -> ToolOutcomeResponse:
    outcome = engine.submit(
        ToolRequest(
            tool=payload.tool,
            capability=payload.capability,
            arguments=payload.arguments,
            request_id=payload.request_id or request_id_var.get(),
        )
    )
    return _outcome_response(outcome)


@router.post("/approvals/{approval_id}/approve", response_model=ToolOutcomeResponse)
def approve(
    approval_id: str,
    engine: ToolEngine = Depends(get_tool_engine),
) -> ToolOutcomeResponse:
    return _outcome_response(engine.approve_and_execute(approval_id))


@router.post("/approvals/{approval_id}/reject", response_model=ToolOutcomeResponse)
def reject(
    approval_id: str,
    engine: ToolEngine = Depends(get_tool_engine),
) -> ToolOutcomeResponse:
    return _outcome_response(engine.reject(approval_id))
