"""品牌规范管理页"""
import streamlit as st
import frontend.api_client as api


def _refresh_brands():
    st.session_state["brands"] = api.list_brands()


def render():
    st.header("📋 品牌规范管理")

    # 初始化品牌列表
    if "brands" not in st.session_state:
        _refresh_brands()

    brands: list[dict] = st.session_state.get("brands", [])

    # ── 已有品牌列表 ──────────────────────────────────────────────────────────
    st.subheader("已有品牌规范")
    if not brands:
        st.info("暂无品牌规范，请在下方上传。")
    else:
        for b in brands:
            col1, col2, col3, col4 = st.columns([3, 2, 3, 2])
            col1.write(f"**{b['brand_name']}**")
            col2.write(b.get("version") or "—")
            col3.write(str(b.get("created_at", ""))[:19])
            with col4:
                c1, c2 = st.columns(2)
                if c1.button("重解析", key=f"reparse_{b['brand_id']}"):
                    with st.spinner("重新解析中…"):
                        try:
                            api.update_brand(b["brand_id"], action="reparse")
                            st.success("重解析完成")
                            _refresh_brands()
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
                if c2.button("删除", key=f"del_{b['brand_id']}"):
                    try:
                        api.delete_brand(b["brand_id"])
                        st.success("已删除")
                        _refresh_brands()
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

    st.divider()

    # ── 上传新品牌规范 ────────────────────────────────────────────────────────
    st.subheader("上传新品牌规范")

    upload_mode = st.radio(
        "上传模式",
        ["单文档", "多文档合并（推荐）"],
        horizontal=True,
        help="多文档合并：将多个规范文档的内容合并后，用 AI 统一解析为一份品牌规范",
    )

    with st.form("upload_brand_form", clear_on_submit=True):
        brand_name = st.text_input("品牌名称", placeholder="例：讯飞品牌")

        if upload_mode == "单文档":
            doc_file = st.file_uploader(
                "规范文档",
                type=["pdf", "pptx", "ppt", "docx", "doc", "xlsx", "xls", "md", "txt"],
            )
            doc_files = None
        else:
            doc_files = st.file_uploader(
                "规范文档（可多选，所有文档将合并解析为一份规范）",
                type=["pdf", "pptx", "ppt", "docx", "doc", "xlsx", "xls", "md", "txt"],
                accept_multiple_files=True,
            )
            doc_file = None
            if doc_files:
                st.caption(f"已选择 {len(doc_files)} 个文档：{', '.join(f.name for f in doc_files)}")

        submitted = st.form_submit_button("上传并解析")

    if submitted:
        if not brand_name:
            st.warning("请填写品牌名称")
        elif upload_mode == "单文档" and not doc_file:
            st.warning("请上传规范文档")
        elif upload_mode == "多文档合并（推荐）" and not doc_files:
            st.warning("请至少上传一个规范文档")
        else:
            if upload_mode == "单文档":
                with st.spinner("正在解析规范文档，约需 30-90 秒…"):
                    try:
                        result = api.create_brand(doc_file.read(), doc_file.name, brand_name)
                        st.success(f"品牌「{result['brand_name']}」创建成功，ID: {result['brand_id']}")
                        _refresh_brands()
                        st.rerun()
                    except Exception as e:
                        st.error(f"上传失败：{e}")
            else:
                n = len(doc_files)
                with st.spinner(f"正在提取 {n} 个文档的内容并合并解析，约需 30-120 秒…"):
                    try:
                        files_data = [(f.name, f.read()) for f in doc_files]
                        result = api.merge_brands(files_data, brand_name)
                        st.success(f"品牌「{result['brand_name']}」创建成功（{n} 个文档合并），ID: {result['brand_id']}")
                        _refresh_brands()
                        st.rerun()
                    except Exception as e:
                        st.error(f"上传失败：{e}")

    st.divider()

    # ── 参考图片管理 ──────────────────────────────────────────────────────────
    st.subheader("参考图片管理（Logo 标准件）")
    if not brands:
        st.info("请先创建品牌规范。")
        return

    brand_options = {b["brand_name"]: b["brand_id"] for b in brands}
    selected_name = st.selectbox("选择品牌", list(brand_options.keys()), key="img_brand_select")
    selected_id   = brand_options[selected_name]

    # 上传参考图片
    img_files = st.file_uploader(
        "上传参考图片（可多选，最多 5 张）",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key="ref_img_uploader",
    )
    img_type = st.selectbox("图片类型", ["logo", "banner", "icon", "other"], key="img_type")
    img_desc = st.text_input("描述（可选）", key="img_desc")

    if st.button("上传参考图片", disabled=not img_files):
        if len(img_files) > 5:
            st.warning("最多上传 5 张")
        else:
            with st.spinner("上传中…"):
                try:
                    result = api.upload_reference_images(
                        selected_id,
                        [(f.name, f.read()) for f in img_files],
                        image_type=img_type,
                        description=img_desc,
                    )
                    st.success(f"已上传：{result['added']}")
                except Exception as e:
                    st.error(f"上传失败：{e}")
