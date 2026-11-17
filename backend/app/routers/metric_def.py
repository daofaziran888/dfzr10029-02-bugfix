"""指标定义 分析看板接口：汇总指标、参数运行、结果导出、口径发布与指标纠错。"""
from __future__ import annotations

import csv
import io
import random
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.schemas import ActionPayload, ActionResult, EntryPayload
from app.services.metric_def import MetricDefService

router = APIRouter(prefix="/api/metric_def", tags=["指标定义"])
service = MetricDefService()
LIST_FIELDS = ["指标编号", "指标名称", "计算公式", "统计粒度", "时间窗口", "筛选条件", "精度位数", "口径版本"]
STATUSES = ["草稿", "已定义", "已发布", "已废弃"]


def csv_cell(value: Any) -> str:
    text = str(value) if value is not None else ""
    if text and text[0] in "=+-@":
        text = "'" + text
    return '"' + text.replace('"', '""') + '"'


@router.get("/summary")
def get_summary() -> dict[str, Any]:
    return {"metrics": [
        {"label": "覆盖数据源", "value": random.randint(12, 45), "trend": random.randint(-12, 25)},
        {"label": "最新指标值", "value": round(random.uniform(0.72, 0.99), 3), "trend": random.randint(-8, 15)},
        {"label": "异常记录", "value": random.randint(0, 8), "trend": -random.randint(1, 10)},
    ]}


@router.get("")
def list_results() -> dict[str, Any]:
    return {"items": service.list_results()}


@router.post("/run")
def run_analysis(payload: EntryPayload) -> dict[str, Any]:
    results = service.run_analysis(payload.values)
    return {"items": results}


@router.get("/export")
def export_entries() -> StreamingResponse:
    items = service.list_results()
    buf = io.StringIO(newline="")
    writer = csv.writer(buf)
    all_keys = ["id"]
    if items:
        all_keys = list(items[0].keys())
    writer.writerow(all_keys)
    for item in items:
        writer.writerow([csv_cell(item.get(k, "")) for k in all_keys])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=metric_def.csv"})


# ---- 口径发布与指标纠错（静态路径需声明在 /{entry_id} 之前） ----

@router.get("/publishes")
def list_publishes() -> dict[str, Any]:
    """历史发布记录列表：每条记录的数值按其来源输入与口径版本重算。"""
    return {"items": service.list_publishes()}


@router.get("/corrections")
def list_corrections() -> dict[str, Any]:
    """指标纠错记录列表：按既有次序返回，同一确认结果不重复显示。"""
    return {"items": service.list_corrections()}


@router.post("/corrections", response_model=ActionResult)
def submit_correction(payload: EntryPayload) -> ActionResult:
    """提交指标纠错：解析来源输入，按新口径版本重算指标结果；重复提交幂等。"""
    record, message, _duplicated = service.submit_correction(payload.values)
    if record is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=record)


@router.get("/corrections/{correction_id}")
def get_correction(correction_id: int) -> dict[str, Any]:
    """纠错详情：重新打开时与既有数据对照，不保留旧残留。"""
    detail = service.get_correction(correction_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"纠错记录 {correction_id} 不存在")
    return detail


@router.get("/diffs")
def list_diffs() -> dict[str, Any]:
    """指标差异接口：消费指标纠错记录，给出修正前后数值与当前采用的发布版本。"""
    return {"items": service.list_diffs()}


@router.post("/diffs/{correction_id}/review", response_model=ActionResult)
def review_diff(correction_id: int) -> ActionResult:
    """复核纠错记录对应的差异记录。"""
    record, message = service.review_diff(correction_id)
    if record is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=record)


@router.put("/{entry_id}/draft", response_model=ActionResult)
def update_draft(entry_id: int, payload: EntryPayload) -> ActionResult:
    """修改指标草稿（统计粒度、计算公式等），处理范围限定在指标草稿。"""
    entry, message = service.update_draft(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/publish", response_model=ActionResult)
def publish_metric(entry_id: int) -> ActionResult:
    """发布指标：校验公式后生成可追溯的发布记录。"""
    record, message = service.publish_metric(entry_id)
    if record is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=record)


@router.post("/{entry_id}/revalidate")
def revalidate_formula(entry_id: int) -> dict[str, Any]:
    """发布页重新校验指标公式，并给出按当前口径版本重算的预览对照。"""
    result, message = service.revalidate_formula(entry_id)
    if result is None:
        raise HTTPException(status_code=404, detail=message)
    return result


@router.get("/{entry_id}")
def get_entry(entry_id: int) -> dict:
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"指标 {entry_id} 不存在")
    return entry
