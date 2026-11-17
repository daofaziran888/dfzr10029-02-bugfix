"""指标定义 分析看板服务：汇总指标、运行分析、口径版本重算与指标纠错。

缺陷修复背景：指标发布后统计粒度发生变更时，历史发布记录仍沿用旧公式算出的
数值，导致指标值与基准差异对不上，运营无法判断哪个差异需要修正。修复方式是把
指标结果改为按口径版本确定性重算：解析已有输入（计算公式、统计粒度、口径版本
等）再按口径版本重算指标结果，处理范围限定在指标草稿及历史发布记录；纠错记录
保留来源输入，输出纠错后的指标结果，保证指标值与基准差异匹配。
"""
from __future__ import annotations

import hashlib
import random
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "metric_def"
PUBLISH_MODULE = "metric_publish"
CORRECTION_MODULE = "metric_correction"
AUDIT_MODULE = "audit"

REQUIRED_FIELDS = ["指标编号", "指标名称", "计算公式"]
STATUS_ORDER = ["草稿", "已定义", "已发布", "已废弃"]
ACTION_RULES = {"提交定义": "已定义", "发布指标": "已发布", "废弃指标": "已废弃"}
NEGATIVE_ACTIONS = []

LIST_FIELDS = ["指标编号", "指标名称", "计算公式", "统计粒度", "时间窗口", "筛选条件", "精度位数", "口径版本"]
# 参与口径重算的来源输入字段：任一变化都会改变重算结果
SOURCE_FIELDS = ["指标编号", "计算公式", "统计粒度", "时间窗口", "筛选条件", "口径版本"]
# 指标草稿允许修改的字段（处理范围限定在指标草稿及历史发布记录）
DRAFT_EDITABLE_FIELDS = ["指标名称", "计算公式", "统计粒度", "时间窗口", "筛选条件", "精度位数"]

PATH_ADOPT_DRAFT = "采用新草稿"
PATH_ROLLBACK_PUBLISH = "回滚旧发布"
CORRECTION_PATHS = [PATH_ADOPT_DRAFT, PATH_ROLLBACK_PUBLISH]
# 指标纠错记录的冲突涉及两种有效路径，二者差异明细的修正范围不同
PATH_SCOPE = {PATH_ADOPT_DRAFT: "全部历史发布记录", PATH_ROLLBACK_PUBLISH: "仅冲突发布记录"}


def _to_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_precision(raw: Any) -> int:
    precision = _to_int(raw)
    if precision is None:
        return 3
    return max(0, min(6, precision))


def compute_metric_result(source: dict[str, Any]) -> dict[str, Any]:
    """解析已有输入，按口径版本确定性重算指标结果。

    同一组来源输入永远得到同一组结果；统计粒度或口径版本变化会体现到数值上，
    差异始终等于指标值 - 对比基准，保证指标值与基准差异匹配。
    """
    precision = _parse_precision(source.get("精度位数"))
    key = "|".join(str(source.get(field) or "") for field in SOURCE_FIELDS)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    value = 0.6 + int(digest[0:8], 16) / 0xFFFFFFFF * 0.4
    baseline = 0.55 + int(digest[8:16], 16) / 0xFFFFFFFF * 0.35
    metric_value = round(value, precision)
    baseline_value = round(baseline, precision)
    return {
        "指标值": metric_value,
        "对比基准": baseline_value,
        "差异": round(metric_value - baseline_value, precision),
    }


def validate_formula(formula: Any) -> tuple[bool, str]:
    """发布前校验指标公式：非空、不含非法字符、括号配对。"""
    text = str(formula or "").strip()
    if not text:
        return False, "计算公式为空"
    if any(ch in text for ch in (";", "\n", "\r")):
        return False, "计算公式包含非法字符"
    closers = {")": "(", "]": "[", "）": "（", "】": "【"}
    stack: list[str] = []
    for ch in text:
        if ch in "([（【":
            stack.append(ch)
        elif ch in closers:
            if not stack or stack.pop() != closers[ch]:
                return False, "计算公式括号不配对"
    if stack:
        return False, "计算公式括号不配对"
    return True, "公式校验通过"


class MetricDefService:
    # ---------- 分析看板 ----------
    def list_results(self) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        results: list[dict] = []
        for row in rows:
            d = dict(row)
            d.update(compute_metric_result(row))
            results.append(d)
        return results

    def run_analysis(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        count = _to_int(params.get("样本范围", params.get("并行数量", "6"))) or 6
        results: list[dict] = []
        for i in range(count):
            metric_value = round(random.uniform(0.62, 1.02), 3)
            baseline = round(random.uniform(0.58, 0.95), 3)
            results.append({
                "id": i + 1,
                "分组": f"分组{(i % 3) + 1}",
                "指标值": metric_value,
                "对比基准": baseline,
                "差异": round(metric_value - baseline, 3),
            })
        return results

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    # ---------- 指标草稿（纠错处理范围之一） ----------
    def update_draft(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"指标 {entry_id} 不存在或已归档"
        if entry.get("status") == "已废弃":
            return None, "已废弃指标不在纠错处理范围内"
        changed: list[str] = []
        for field in DRAFT_EDITABLE_FIELDS:
            if field not in values or values[field] is None:
                continue
            new_value = str(values[field]).strip()
            if new_value and new_value != str(entry.get(field) or ""):
                entry[field] = new_value
                changed.append(field)
        if not changed:
            return None, "草稿内容未发生变化"
        message = f"指标草稿已更新：{'、'.join(changed)}"
        if self._draft_conflict(entry):
            message += "；与当前发布记录的公式或粒度不一致，需提交指标纠错"
        return entry, message

    def _draft_conflict(self, entry: dict[str, Any]) -> bool:
        """同一指标的历史发布记录与刚修改的草稿公式/粒度冲突判定。"""
        if entry.get("status") != "已发布":
            return False
        adopted = self._adopted_publish(_to_int(entry.get("id")))
        if adopted is None:
            return False
        source = adopted.get("来源输入") or {}
        return any(
            str(entry.get(field) or "") != str(source.get(field) or "")
            for field in ("计算公式", "统计粒度")
        )

    # ---------- 历史发布记录 ----------
    def list_publishes(self) -> list[dict[str, Any]]:
        """发布记录列表：数值按来源输入重算，保证与各自口径版本匹配。"""
        records: list[dict] = []
        for record in store.rows(PUBLISH_MODULE):
            d = dict(record)
            source = d.get("来源输入") or {}
            if source:
                d.update(compute_metric_result(source))
            records.append(d)
        return records

    def _adopted_publish(self, metric_id: int | None) -> dict[str, Any] | None:
        if metric_id is None:
            return None
        for record in store.rows(PUBLISH_MODULE):
            if _to_int(record.get("指标id")) == metric_id and record.get("当前采用"):
                return record
        return None

    def publish_metric(self, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        """发布指标：先校验公式，再按当前口径版本生成可追溯的发布记录。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"指标 {entry_id} 不存在或已归档"
        if entry.get("status") == "已废弃":
            return None, "已废弃指标不能发布"
        ok, reason = validate_formula(entry.get("计算公式"))
        if not ok:
            return None, f"公式校验未通过：{reason}"
        record = self._create_publish_record(entry, str(entry.get("口径版本") or "V1.0"))
        entry["status"] = "已发布"
        entry["pending"] = False
        entry["abnormal"] = False
        return record, f"指标已发布，生成发布记录 V{record['版本序号']}"

    def _create_publish_record(self, entry: dict[str, Any], caliber_version: str) -> dict[str, Any]:
        rows = store.rows(PUBLISH_MODULE)
        metric_id = _to_int(entry.get("id"))
        for row in rows:
            if _to_int(row.get("指标id")) == metric_id:
                row["当前采用"] = False
                if row.get("状态") == "已发布":
                    row["状态"] = "被取代"
        source = {field: entry.get(field) for field in LIST_FIELDS}
        source["口径版本"] = caliber_version
        version_no = max(
            (_to_int(row.get("版本序号")) or 0 for row in rows if _to_int(row.get("指标id")) == metric_id),
            default=0,
        ) + 1
        record: dict[str, Any] = {
            "id": max((_to_int(row.get("id")) or 0 for row in rows), default=0) + 1,
            "指标id": metric_id,
            "指标编号": entry.get("指标编号"),
            "指标名称": entry.get("指标名称"),
            "版本序号": version_no,
            "口径版本": caliber_version,
            "来源输入": source,
            "计算公式": entry.get("计算公式"),
            "统计粒度": entry.get("统计粒度"),
            "发布时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "当前采用": True,
            "状态": "已发布",
        }
        record.update(compute_metric_result(source))
        rows.append(record)
        return record

    def revalidate_formula(self, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        """发布页重新校验指标公式，并给出按当前口径版本重算的预览对照。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"指标 {entry_id} 不存在或已归档"
        ok, reason = validate_formula(entry.get("计算公式"))
        adopted = self._adopted_publish(entry_id)
        adopted_source = (adopted or {}).get("来源输入") or {}
        result = {
            "校验通过": ok,
            "校验说明": reason,
            "重算预览": compute_metric_result(entry),
            "当前发布结果": compute_metric_result(adopted_source) if adopted_source else None,
            "当前采用版本": f"V{adopted['版本序号']}（{adopted['口径版本']}）" if adopted else None,
            "草稿与发布冲突": self._draft_conflict(entry),
        }
        return result, reason

    # ---------- 指标纠错 ----------
    def list_corrections(self) -> list[dict[str, Any]]:
        """纠错记录列表：沿用既有次序返回，并按幂等键去重，避免同一确认结果在列表重复显示。"""
        seen: set[str] = set()
        results: list[dict] = []
        for row in store.rows(CORRECTION_MODULE):
            key = str(row.get("幂等键") or f"id:{row.get('id')}")
            if key in seen:
                continue
            seen.add(key)
            results.append(dict(row))
        return results

    def get_correction(self, correction_id: int) -> dict[str, Any] | None:
        """纠错详情：重新打开时按来源输入再算一遍，与既有数据对照，不留旧残留。"""
        record = store.find(CORRECTION_MODULE, correction_id)
        if record is None:
            return None
        detail = dict(record)
        source = record.get("来源输入") or {}
        new_version = str(record.get("新口径版本") or "").strip()
        if source and new_version:
            recalc_source = dict(source)
            recalc_source["口径版本"] = new_version
            fresh = compute_metric_result(recalc_source)
            stored = record.get("修正后") or {}
            consistent = all(fresh[key] == stored.get(key) for key in ("指标值", "对比基准", "差异"))
            detail["对照重算"] = fresh
            detail["对照结果"] = "一致" if consistent else "不一致"
        else:
            detail["对照重算"] = None
            detail["对照结果"] = "来源输入缺失，无法对照"
        return detail

    def submit_correction(self, payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str, bool]:
        """提交指标纠错：解析发布记录的来源输入，按新口径版本重算指标结果。

        - 处理范围限定在指标草稿及历史发布记录，纠错记录保留来源输入；
        - 历史发布记录和新的口径版本在同一次纠错中确定引用关系；
        - 同一（发布记录、新口径版本、处理路径）重复提交不会多出第二份确认结果；
        - 报错、不生效或丢失的记录同样写入纠错记录，并给出不一致原因。
        """
        publish_id = _to_int(payload.get("发布记录id"))
        new_version = str(payload.get("新口径版本") or "").strip()
        path = str(payload.get("处理路径") or "").strip()
        if path not in CORRECTION_PATHS:
            return None, f"处理路径「{path}」无效，可选：{'、'.join(CORRECTION_PATHS)}", False
        if not new_version:
            return None, "新口径版本不能为空", False
        idem_key = f"{publish_id}|{new_version}|{path}"
        for row in store.rows(CORRECTION_MODULE):
            if row.get("幂等键") == idem_key:
                return dict(row), "已存在相同纠错确认结果，本次不重复生成", True

        record = store.find(PUBLISH_MODULE, publish_id) if publish_id is not None else None
        if record is None:
            # 丢失：发布记录找不到，仍写入纠错记录说明原因
            correction = self._write_correction({
                "指标id": None,
                "指标编号": str(payload.get("指标编号") or ""),
                "指标名称": "",
                "发布记录id": publish_id,
                "发布版本序号": None,
                "处理路径": path,
                "新口径版本": new_version,
                "来源输入": {},
                "修正前": {},
                "修正后": {},
                "修正范围": PATH_SCOPE[path],
                "差异明细": [],
                "不一致原因": "关联发布记录丢失，无法定位来源输入",
                "状态": "确认失败",
                "幂等键": idem_key,
            })
            return correction, "关联发布记录丢失，纠错记录已写入并标记确认失败", False

        metric_id = _to_int(record.get("指标id"))
        metric = store.find(MODULE, metric_id) if metric_id is not None else None
        source = dict(record.get("来源输入") or {})
        # 报错：来源输入解析失败
        parse_error = self._parse_source_error(source)
        if parse_error:
            correction = self._write_correction({
                "指标id": metric_id,
                "指标编号": record.get("指标编号"),
                "指标名称": record.get("指标名称"),
                "发布记录id": record.get("id"),
                "发布版本序号": record.get("版本序号"),
                "处理路径": path,
                "新口径版本": new_version,
                "来源输入": source,
                "修正前": {},
                "修正后": {},
                "修正范围": PATH_SCOPE[path],
                "差异明细": [],
                "不一致原因": f"来源输入解析失败：{parse_error}",
                "状态": "确认失败",
                "幂等键": idem_key,
            })
            return correction, f"来源输入解析失败：{parse_error}", False
        # 不生效：新口径版本与发布记录一致，重算不会带来变化
        if new_version == str(record.get("口径版本") or ""):
            correction = self._write_correction({
                "指标id": metric_id,
                "指标编号": record.get("指标编号"),
                "指标名称": record.get("指标名称"),
                "发布记录id": record.get("id"),
                "发布版本序号": record.get("版本序号"),
                "处理路径": path,
                "新口径版本": new_version,
                "来源输入": source,
                "修正前": compute_metric_result(source),
                "修正后": {},
                "修正范围": PATH_SCOPE[path],
                "差异明细": [],
                "不一致原因": "新口径版本与发布记录一致，重算不生效",
                "状态": "确认失败",
                "幂等键": idem_key,
            })
            return correction, "新口径版本与发布记录一致，重算不生效", False

        before = compute_metric_result(source)
        after_source = dict(source)
        after_source["口径版本"] = new_version
        after = compute_metric_result(after_source)

        # 两种有效路径的差异明细修正范围不同
        if path == PATH_ADOPT_DRAFT:
            scope_records = [row for row in store.rows(PUBLISH_MODULE) if _to_int(row.get("指标id")) == metric_id]
        else:
            scope_records = [record]
        details: list[dict[str, Any]] = []
        for item in scope_records:
            item_source = dict(item.get("来源输入") or {})
            if not item_source:
                continue
            item_after_source = dict(item_source)
            item_after_source["口径版本"] = new_version
            details.append({
                "发布记录id": item.get("id"),
                "版本序号": item.get("版本序号"),
                "修正前": compute_metric_result(item_source),
                "修正后": compute_metric_result(item_after_source),
            })

        correction = self._write_correction({
            "指标id": metric_id,
            "指标编号": record.get("指标编号"),
            "指标名称": record.get("指标名称"),
            "发布记录id": record.get("id"),
            "发布版本序号": record.get("版本序号"),
            "处理路径": path,
            "新口径版本": new_version,
            "来源输入": source,
            "修正前": before,
            "修正后": after,
            "修正范围": PATH_SCOPE[path],
            "差异明细": details,
            "不一致原因": "",
            "状态": "已确认",
            "幂等键": idem_key,
        })

        message = "纠错已确认"
        if metric is not None:
            if path == PATH_ADOPT_DRAFT:
                # 采用新草稿：以草稿口径生成新的可追溯发布版本，修正范围覆盖全部历史发布记录
                metric["口径版本"] = new_version
                new_record = self._create_publish_record(metric, new_version)
                message = f"纠错已确认：采用新草稿生成发布记录 V{new_record['版本序号']}，修正范围覆盖全部历史发布记录"
            else:
                # 回滚旧发布：草稿公式与粒度回退到发布记录口径，发布记录仍是当前采用版本
                metric["计算公式"] = source.get("计算公式", metric.get("计算公式"))
                metric["统计粒度"] = source.get("统计粒度", metric.get("统计粒度"))
                metric["口径版本"] = new_version
                message = f"纠错已确认：已回滚到发布记录 V{record.get('版本序号')} 的口径，仅修正冲突发布记录"
        return correction, message, False

    def _parse_source_error(self, source: dict[str, Any]) -> str | None:
        if not source:
            return "来源输入为空"
        ok, reason = validate_formula(source.get("计算公式"))
        if not ok:
            return reason
        if not str(source.get("统计粒度") or "").strip():
            return "统计粒度为空"
        return None

    def _write_correction(self, values: dict[str, Any]) -> dict[str, Any]:
        rows = store.rows(CORRECTION_MODULE)
        record: dict[str, Any] = {
            "id": max((_to_int(row.get("id")) or 0 for row in rows), default=0) + 1,
            "复核状态": "待复核",
            "提交时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        record.update(values)
        rows.append(record)
        self._write_audit(record)
        return dict(record)

    def _write_audit(self, correction: dict[str, Any]) -> None:
        """沿着既有业务数据流，把纠错结果跨业务模块写入数据审计。"""
        rows = store.rows(AUDIT_MODULE)
        seq = max((_to_int(row.get("id")) or 0 for row in rows), default=0) + 1
        rows.append({
            "id": seq,
            "status": "已记录",
            "pending": False,
            "abnormal": correction.get("状态") != "已确认",
            "记录编号": f"AUDI-{seq:04d}",
            "操作类型": "指标纠错",
            "操作人": "系统",
            "操作对象": correction.get("指标编号") or "未知指标",
            "操作时间": correction.get("提交时间"),
            "变更内容": f"{correction.get('处理路径')}→{correction.get('新口径版本')}（{correction.get('状态')}）",
            "审计结果": correction.get("状态"),
            "记录状态": correction.get("复核状态"),
        })

    # ---------- 指标差异（消费纠错记录） ----------
    def list_diffs(self) -> list[dict[str, Any]]:
        """指标差异接口：消费纠错记录，附上当前采用的发布版本，供差异页复核。"""
        diffs: list[dict[str, Any]] = []
        for correction in self.list_corrections():
            adopted = self._adopted_publish(_to_int(correction.get("指标id")))
            diffs.append({
                "纠错id": correction.get("id"),
                "指标编号": correction.get("指标编号"),
                "指标名称": correction.get("指标名称"),
                "处理路径": correction.get("处理路径"),
                "新口径版本": correction.get("新口径版本"),
                "修正前": correction.get("修正前"),
                "修正后": correction.get("修正后"),
                "修正范围": correction.get("修正范围"),
                "差异明细": correction.get("差异明细"),
                "当前采用发布版本": f"V{adopted['版本序号']}（{adopted['口径版本']}）" if adopted else "无发布记录",
                "不一致原因": correction.get("不一致原因"),
                "状态": correction.get("状态"),
                "复核状态": correction.get("复核状态"),
                "提交时间": correction.get("提交时间"),
            })
        return diffs

    def review_diff(self, correction_id: int) -> tuple[dict[str, Any] | None, str]:
        """复核纠错记录对应的差异；已复核的重复提交不会多出第二份确认结果。"""
        record = store.find(CORRECTION_MODULE, correction_id)
        if record is None:
            return None, f"纠错记录 {correction_id} 不存在"
        if record.get("状态") != "已确认":
            return None, "仅已确认的纠错记录可复核"
        if record.get("复核状态") == "已复核":
            return dict(record), "该纠错记录已复核，无需重复确认"
        record["复核状态"] = "已复核"
        return dict(record), "复核完成"
