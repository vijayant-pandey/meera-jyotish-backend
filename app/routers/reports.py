from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import require_current_user, require_db
from app.models import User
from app.schemas import (
    DivisionalChartEntry,
    DashaRouteResponse,
    KundaliChartRouteResponse,
    KundaliReport,
    KundaliRequest,
    KundaliResponse,
)
from app.services.astrology import calculate_kundali
from app.services.report_store import create_report, get_report_for_user

router = APIRouter(prefix="/api", tags=["reports"])


@router.post("/kundali/generate", response_model=KundaliResponse)
async def generate_kundali(payload: KundaliRequest) -> KundaliResponse:
    if payload.place.precision == "country":
        raise HTTPException(
            status_code=400,
            detail="Country-level birthplace is not accurate enough. Select a city or enter manual coordinates.",
        )

    try:
        return calculate_kundali(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Kundali generation failed: {exc}") from exc


@router.post("/reports", response_model=KundaliReport)
async def create_report_route(
    payload: KundaliRequest,
    db: Session = Depends(require_db),
    user: User = Depends(require_current_user),
) -> KundaliReport:
    result = await generate_kundali(payload)
    return create_report(db, user, payload, result)


@router.get("/reports/{report_id}", response_model=KundaliReport)
async def get_report(
    report_id: str,
    db: Session = Depends(require_db),
    user: User = Depends(require_current_user),
) -> KundaliReport:
    report = get_report_for_user(db, report_id, user)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return report


@router.get("/reports/{report_id}/charts/{chart_key}", response_model=KundaliChartRouteResponse)
async def get_report_chart(
    report_id: str,
    chart_key: str,
    db: Session = Depends(require_db),
    user: User = Depends(require_current_user),
) -> KundaliChartRouteResponse:
    report = await get_report(report_id, db, user)
    normalized_chart_key = chart_key.upper()
    selected_chart = next(
        (chart for chart in report.result.divisional_charts if chart.key == normalized_chart_key),
        None,
    )
    if selected_chart is None:
        raise HTTPException(status_code=404, detail="Chart not found for this report.")

    return KundaliChartRouteResponse(
        report_id=report.id,
        created_at=report.created_at,
        name=report.request.name,
        birth_context=report.result.birth_context,
        selected_chart=selected_chart,
        available_charts=[
            DivisionalChartEntry(
                key=chart.key,
                factor=chart.factor,
                title=chart.title,
                focus=chart.focus,
                chart=chart.chart,
            )
            for chart in report.result.divisional_charts
        ],
    )


@router.get("/reports/{report_id}/dasha", response_model=DashaRouteResponse)
async def get_report_dasha(
    report_id: str,
    db: Session = Depends(require_db),
    user: User = Depends(require_current_user),
) -> DashaRouteResponse:
    report = await get_report(report_id, db, user)
    return DashaRouteResponse(
        report_id=report.id,
        created_at=report.created_at,
        name=report.request.name,
        birth_context=report.result.birth_context,
        dasha=report.result.dasha,
    )
