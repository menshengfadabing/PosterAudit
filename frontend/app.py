"""
Streamlit 前端主入口
"""
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中（Streamlit 直接运行时需要）
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st

from frontend.pages import audit, brands, history


def main():
    st.set_page_config(
        page_title="品牌合规性审核平台",
        page_icon="🎨",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # 侧边栏导航
    st.sidebar.title("🎨 品牌合规性审核")
    st.sidebar.markdown("---")

    page = st.sidebar.radio(
        "导航",
        ["🔍 审核", "📋 品牌管理", "📁 历史"],
        label_visibility="collapsed"
    )

    st.sidebar.markdown("---")
    st.sidebar.caption("Powered by DeepSeek + Doubao")

    # 路由到对应页面
    if page == "🔍 审核":
        audit.render()
    elif page == "📋 品牌管理":
        brands.render()
    elif page == "📁 历史":
        history.render()


if __name__ == "__main__":
    main()
