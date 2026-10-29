"""HTTP routes. Heavy endpoints are plain `def` so FastAPI runs them in a
worker thread instead of blocking the event loop."""

import traceback
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from tripweaver.api.schemas import ApprovalRequest, TravelRequest
from tripweaver.service import resume_travel_agent, run_travel_agent

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

router = APIRouter()


def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "error": message},
    )


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )


@router.post("/api/travel")
def travel_planner(request_data: TravelRequest):
    try:
        user_message = request_data.message.strip()

        if not user_message:
            return _error(400, "Message cannot be empty.")

        result = run_travel_agent(
            user_input=user_message,
            thread_id=request_data.thread_id,
        )
        return JSONResponse(content={"success": True, **result})

    except Exception as exc:
        print("ERROR:", exc)
        traceback.print_exc()
        return _error(500, str(exc))


@router.post("/api/travel/approve")
def approve_travel_plan(request_data: ApprovalRequest):
    try:
        if not request_data.approved and not request_data.feedback.strip():
            return _error(
                400,
                "Please provide revision feedback when rejecting the draft.",
            )

        result = resume_travel_agent(
            thread_id=request_data.thread_id,
            approved=request_data.approved,
            feedback=request_data.feedback,
        )
        return JSONResponse(content={"success": True, **result})

    except Exception as exc:
        print("APPROVAL ERROR:", exc)
        traceback.print_exc()
        return _error(500, str(exc))


@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "message": "TripMate AI API is running",
        "features": [
            "supervisor_agent",
            "input_guardrail",
            "human_in_the_loop",
        ],
    }


@router.get("/favicon.ico")
async def favicon():
    return JSONResponse(content={})
