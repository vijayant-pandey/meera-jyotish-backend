from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KundaliReportModel, User
from app.schemas import KundaliReport, KundaliRequest, KundaliResponse
from app.services.astrology import calculate_kundali


def create_report(
    db: Session,
    user: User,
    payload: KundaliRequest,
    result: KundaliResponse,
) -> KundaliReport:
    report_model = KundaliReportModel(
        id=uuid4().hex[:12],
        user_id=user.id,
        request_json=json.dumps(payload.model_dump(mode="json", by_alias=True)),
        result_json=json.dumps(result.model_dump(mode="json", by_alias=True)),
    )
    db.add(report_model)
    db.commit()
    db.refresh(report_model)
    return to_schema(report_model)


def get_report_for_user(db: Session, report_id: str, user: User) -> KundaliReport | None:
    report_model = db.scalar(
        select(KundaliReportModel).where(
            KundaliReportModel.id == report_id,
            KundaliReportModel.user_id == user.id,
        )
    )
    if report_model is None:
        return None
    return to_schema(report_model)


def to_schema(report_model: KundaliReportModel) -> KundaliReport:
    created_at = report_model.created_at
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    request = KundaliRequest.model_validate(json.loads(report_model.request_json))
    result = KundaliResponse.model_validate(json.loads(report_model.result_json))
    calculated = None
    chalit = next((chart for chart in result.divisional_charts if chart.key == "CHALIT"), None)
    if (
        chalit is None
        or [house.house_number for house in chalit.chart.houses] != list(range(1, 13))
        or chalit.focus != "Planets placed by Sripati bhava boundaries"
    ):
        # Enrich older reports and replace earlier Chalit house-system representations.
        calculated = calculate_kundali(request)
        result.divisional_charts = calculated.divisional_charts

    # Rebuild only the Dasha timeline from the backend's current calculation.
    # Legacy JSON has no calculation-version field, so a schema default cannot
    # reliably identify dates produced with an older year convention.
    calculated = calculated or calculate_kundali(request)
    result.dasha = calculated.dasha
    return KundaliReport(
        id=report_model.id,
        created_at=created_at,
        user_id=report_model.user_id,
        request=request,
        result=result,
    )
