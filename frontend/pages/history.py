"""
审核历史页面
"""
import streamlit as st
from datetime import datetime
from typing import Optional

from frontend import api_client as api
from frontend.config import PAGE_SIZE


def _format_datetime(dt_str: Optional[str]) -> str:
    """格式化时间字符串"""
    if not dt_str:
        return "-"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return dt_str


def _status_badge(status: str) -> str:
    """返回状态徽章"""
    status_map = {
        "pending": "⏳ 等待中",
        "processing": "⚙️ 处理中",
        "completed": "✅ 已完成",
        "failed": "❌ 失败"
    }
    return status_map.get(status.lower(), status)


def _render_task_detail(task: dict):
    """渲染任务详情（可展开）"""
    with st.expander(f"任务 {task['id'][:8]}... - {_status_badge(task['status'])}", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.text(f"品牌ID: {task.get('brand_id', '-')}")
            st.text(f"创建时间: {_format_datetime(task.get('created_at'))}")
        with col2:
            st.text(f"状态: {task.get('status', '-')}")
            st.text(f"更新时间: {_format_datetime(task.get('updated_at'))}")

        # 输入元数据
        input_meta = task.get("input_meta") or {}
        if input_meta:
            st.subheader("输入参数")
            st.json(input_meta)

        # 错误信息
        if task.get("error"):
            st.error(f"错误: {task['error']}")

        # 审核结果
        results = task.get("results")
        if results:
            st.subheader("审核结果")
            if isinstance(results, list):
                for idx, result in enumerate(results, 1):
                    st.markdown(f"**图片 {idx}**")
                    status = (result.get("status") or "review").lower()
                    score = result.get("score", 0)
                    st.metric("评分", f"{score}/100", delta=None)
                    st.text(f"状态: {status}")

                    rule_checks = result.get("rule_checks") or result.get("results") or []
                    if rule_checks:
                        st.text(f"规则检查: {len(rule_checks)} 项")

                    if idx < len(results):
                        st.divider()
            else:
                st.json(results)


def render():
    """渲染历史页面"""
    st.header("📁 审核历史")

    # 筛选栏
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        # 品牌筛选
        try:
            brands = api.list_brands()
            brand_options = {"全部品牌": None}
            brand_options.update({b["name"]: b["id"] for b in brands})
            selected_brand_name = st.selectbox("筛选品牌", list(brand_options.keys()))
            selected_brand_id = brand_options[selected_brand_name]
        except Exception as e:
            st.error(f"加载品牌列表失败: {e}")
            selected_brand_id = None

    with col2:
        # 页码
        if "history_page" not in st.session_state:
            st.session_state["history_page"] = 1
        page = st.number_input("页码", min_value=1, value=st.session_state["history_page"], step=1)
        st.session_state["history_page"] = page

    with col3:
        # 刷新按钮
        if st.button("🔄 刷新", use_container_width=True):
            st.rerun()

    # 加载历史记录
    try:
        history = api.list_history(
            brand_id=selected_brand_id,
            page=page,
            page_size=PAGE_SIZE
        )

        tasks = history.get("items", [])
        total = history.get("total", 0)

        if not tasks:
            st.info("暂无审核记录")
            return

        # 显示统计
        st.caption(f"共 {total} 条记录，当前第 {page} 页")

        # 渲染任务列表
        for task in tasks:
            _render_task_detail(task)

        # 分页导航
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            if page > 1:
                if st.button("⬅️ 上一页"):
                    st.session_state["history_page"] = page - 1
                    st.rerun()
        with col3:
            if page * PAGE_SIZE < total:
                if st.button("下一页 ➡️"):
                    st.session_state["history_page"] = page + 1
                    st.rerun()

    except Exception as e:
        st.error(f"加载历史记录失败: {e}")
