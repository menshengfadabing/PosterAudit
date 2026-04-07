"""审核历史页面"""
from datetime import datetime
from typing import Optional

import streamlit as st

from frontend import api_client as api
from frontend.config import PAGE_SIZE
from frontend.pages.audit import _render_result  # 复用审核结果渲染


def _format_dt(dt_str: Optional[str]) -> str:
    if not dt_str:
        return "-"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(dt_str)


_STATUS_BADGE = {
    "pending":    "⏳ 等待中",
    "running":    "⚙️ 处理中",
    "completed":  "✅ 已完成",
    "failed":     "❌ 失败",
}


def _render_task(task: dict):
    task_id   = task.get("task_id") or task.get("id", "unknown")
    status    = task.get("status", "")
    badge     = _STATUS_BADGE.get(status, status)
    results   = task.get("results") or []
    n_images  = task.get("image_count") or len(results)
    created   = _format_dt(task.get("created_at"))

    header = f"{badge}  |  {created}  |  {n_images} 张图片  |  `{task_id[:8]}`"

    with st.expander(header, expanded=False):
        # ── 删除按钮 ──────────────────────────────────────────────────────────
        if st.button("🗑️ 删除此记录", key=f"del_{task_id}"):
            try:
                api.delete_task(task_id)
                st.success("已删除")
                st.rerun()
            except Exception as e:
                st.error(f"删除失败：{e}")
            return

        if status == "failed":
            st.error(f"审核失败：{task.get('error', '未知错误')}")
            return

        if not results:
            st.info("暂无结果数据")
            return

        # ── 多图用 tabs，单图直接渲染 ─────────────────────────────────────────
        # 每个 result 结构：{"file_name": ..., "status": "success"/"error", "report": {...}}
        if len(results) == 1:
            r = results[0]
            if r.get("status") == "error":
                st.error(f"审核失败：{r.get('error', '')}")
            else:
                _render_result(r.get("report") or r, label=r.get("file_name", ""))
        else:
            tab_labels = [
                r.get("file_name") or f"图片 {i+1}"
                for i, r in enumerate(results)
            ]
            tabs = st.tabs(tab_labels)
            for tab, r in zip(tabs, results):
                with tab:
                    if r.get("status") == "error":
                        st.error(f"审核失败：{r.get('error', '')}")
                    else:
                        _render_result(r.get("report") or r, label=r.get("file_name", ""))


def render():
    st.header("📁 审核历史")

    # ── 筛选栏 ────────────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns([3, 1, 1])

    with col1:
        try:
            brands = api.list_brands()
            brand_options: dict[str, Optional[str]] = {"全部品牌": None}
            brand_options.update({b["brand_name"]: b["brand_id"] for b in brands})
        except Exception as e:
            st.error(f"加载品牌列表失败：{e}")
            brand_options = {"全部品牌": None}
        selected_brand_name = st.selectbox("筛选品牌", list(brand_options.keys()))
        selected_brand_id   = brand_options[selected_brand_name]

    with col2:
        if "history_page" not in st.session_state:
            st.session_state["history_page"] = 1
        page = st.number_input("页码", min_value=1,
                               value=st.session_state["history_page"], step=1)
        st.session_state["history_page"] = page

    with col3:
        st.write("")   # 对齐
        st.write("")
        if st.button("🔄 刷新", use_container_width=True):
            st.rerun()

    # ── 历史列表 ──────────────────────────────────────────────────────────────
    try:
        data  = api.list_history(brand_id=selected_brand_id,
                                 page=page, page_size=PAGE_SIZE)
        tasks = data.get("items", [])
        total = data.get("total", 0)
    except Exception as e:
        st.error(f"加载历史记录失败：{e}")
        return

    if not tasks:
        st.info("暂无审核记录")
        return

    st.caption(f"共 {total} 条记录，第 {page} 页")

    for task in tasks:
        _render_task(task)

    # ── 分页 ─────────────────────────────────────────────────────────────────
    col_prev, _, col_next = st.columns([1, 3, 1])
    if page > 1:
        if col_prev.button("⬅️ 上一页", use_container_width=True):
            st.session_state["history_page"] = page - 1
            st.rerun()
    if page * PAGE_SIZE < total:
        if col_next.button("下一页 ➡️", use_container_width=True):
            st.session_state["history_page"] = page + 1
            st.rerun()
