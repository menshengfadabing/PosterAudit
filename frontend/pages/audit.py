"""设计稿审核页"""
import time

import streamlit as st

import frontend.api_client as api
from frontend.config import POLL_INTERVAL


_STATUS_ICON = {"pass": "🟢", "review": "🟡", "fail": "🔴"}
_STATUS_LABEL = {"pass": "合规", "review": "需复核", "fail": "不合规"}


def _render_result(result: dict, label: str = ""):
    """渲染单张图片的审核结果"""
    status = (result.get("status") or "review").lower()
    icon  = _STATUS_ICON.get(status, "⚪")
    label_text = _STATUS_LABEL.get(status, status.upper())

    st.markdown(f"### {icon} {label} — **{label_text}**")
    st.caption(result.get("summary", ""))

    # 规则检查清单
    rule_checks = result.get("rule_checks") or result.get("results") or []
    if rule_checks:
        rows = []
        for rc in rule_checks:
            s = (rc.get("s") or rc.get("status") or "r").lower()
            status_map = {"p": "pass", "f": "fail", "r": "review",
                          "pass": "pass", "fail": "fail", "review": "review"}
            s = status_map.get(s, s)
            rows.append({
                "规则": rc.get("id") or rc.get("rule_id", ""),
                "内容": rc.get("rule_content", ""),
                "状态": {"pass": "✅ PASS", "fail": "❌ FAIL", "review": "⚠️ REVIEW"}.get(s, s),
                "置信度": f"{rc.get('c') or rc.get('confidence', 0):.0%}",
            })
        # 按状态排序：FAIL → REVIEW → PASS
        order = {"❌ FAIL": 0, "⚠️ REVIEW": 1, "✅ PASS": 2}
        rows.sort(key=lambda r: order.get(r["状态"], 3))
        st.dataframe(rows, use_container_width=True, hide_index=True)

    # 问题列表
    issues = result.get("issues", [])
    if issues:
        with st.expander(f"⚠️ 发现 {len(issues)} 个问题"):
            for iss in issues:
                sev = iss.get("severity", "")
                st.markdown(f"- **{iss.get('description', '')}**  \n  💡 {iss.get('suggestion', '')}")

    # 检测到的颜色
    detection = result.get("detection") or {}
    colors = detection.get("colors", [])
    if colors:
        with st.expander("🎨 检测到的颜色"):
            cols = st.columns(min(len(colors), 6))
            for i, c in enumerate(colors[:6]):
                with cols[i]:
                    hex_val = c.get("hex", "#ccc")
                    pct = c.get("percent", 0)
                    st.markdown(
                        f'<div style="background:{hex_val};height:32px;border-radius:4px"></div>'
                        f'<p style="font-size:11px;text-align:center">{hex_val}<br>{pct:.0%}</p>',
                        unsafe_allow_html=True,
                    )


def render():
    st.header("🔍 设计稿审核")

    # ── 侧边栏：参数配置 ──────────────────────────────────────────────────────
    with st.sidebar:
        st.subheader("审核配置")

        # 品牌选择
        try:
            brands = api.list_brands()
        except Exception as e:
            st.error(f"无法连接到 API：{e}")
            return

        if not brands:
            st.warning("请先在「品牌规范管理」页面上传品牌规范。")
            return

        brand_options = {b["brand_name"]: b["brand_id"] for b in brands}
        selected_brand_name = st.selectbox("品牌规范", list(brand_options.keys()))
        selected_brand_id   = brand_options[selected_brand_name]

        compression = st.selectbox(
            "压缩预设",
            ["balanced", "high_quality", "high_compression", "no_compression"],
            format_func=lambda x: {
                "balanced": "均衡（推荐）",
                "high_quality": "高质量",
                "high_compression": "高压缩",
                "no_compression": "不压缩",
            }.get(x, x),
        )

        batch_size_opt = st.selectbox(
            "批次大小",
            [0, 3, 5, 8, 10],
            format_func=lambda x: "自动优化" if x == 0 else f"{x} 张/批",
        )
        batch_size = None if batch_size_opt == 0 else batch_size_opt

    # ── 主区域：上传图片 ──────────────────────────────────────────────────────
    uploaded = st.file_uploader(
        "上传设计稿（支持多选，最多 100 张）",
        type=["png", "jpg", "jpeg", "webp", "bmp"],
        accept_multiple_files=True,
    )

    if not uploaded:
        st.info("请上传待审核的设计稿图片。")
        return

    st.write(f"已选择 **{len(uploaded)}** 张图片")
    # 预览缩略图（最多显示 5 张）
    preview_cols = st.columns(min(len(uploaded), 5))
    for i, f in enumerate(uploaded[:5]):
        preview_cols[i].image(f, use_container_width=True, caption=f.name[:12])

    if st.button("🚀 开始审核", type="primary"):
        images = [(f.name, f.read()) for f in uploaded]

        with st.spinner("提交审核任务…"):
            try:
                resp = api.submit_audit(
                    brand_id=selected_brand_id,
                    images=images,
                    mode="async",
                    batch_size=batch_size,
                    compression=compression,
                )
            except Exception as e:
                st.error(f"提交失败：{e}")
                return

        task_id = resp.get("task_id")
        if not task_id:
            st.error("未收到 task_id，请检查 API。")
            return

        # ── 轮询任务结果 ──────────────────────────────────────────────────────
        progress = st.progress(0, text="等待审核结果…")
        start = time.time()
        MAX_WAIT = 300

        while True:
            elapsed = time.time() - start
            if elapsed > MAX_WAIT:
                st.error("审核超时，请稍后在「审核历史」页查看结果。")
                break

            pct = min(int(elapsed / MAX_WAIT * 90), 90)
            progress.progress(pct, text=f"审核中… {int(elapsed)}s")

            try:
                task = api.get_task(task_id)
            except Exception as e:
                st.error(f"查询任务失败：{e}")
                break

            if task["status"] == "completed":
                progress.progress(100, text="审核完成！")
                st.success(f"审核完成，共 {len(images)} 张")

                results = task.get("results") or []
                if len(results) == 1:
                    _render_result(results[0])
                else:
                    tabs = st.tabs([f"图片 {i+1}：{uploaded[i].name[:15]}" for i in range(len(results))])
                    for i, (tab, result) in enumerate(zip(tabs, results)):
                        with tab:
                            _render_result(result, label=uploaded[i].name)

                # 导出按钮
                import json
                st.download_button(
                    "⬇️ 导出 JSON",
                    data=json.dumps(results, ensure_ascii=False, indent=2, default=str),
                    file_name=f"audit_{task_id[:8]}.json",
                    mime="application/json",
                )
                break

            elif task["status"] == "failed":
                progress.empty()
                st.error(f"审核失败：{task.get('error', '未知错误')}")
                break

            time.sleep(POLL_INTERVAL)
