"""设置页面 - API 配置管理"""
import os
from pathlib import Path

import httpx
import streamlit as st


def _env_path() -> Path:
    """返回项目根目录的 .env 文件路径"""
    return Path(__file__).resolve().parent.parent.parent / ".env"


def _load_env() -> dict:
    """从 .env 文件读取所有键值对"""
    env = {}
    p = _env_path()
    if not p.exists():
        return env
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    return env


def _save_env(env: dict):
    """将键值对写回 .env 文件（保留注释行）"""
    p = _env_path()
    existing_lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []

    written_keys = set()
    new_lines = []
    for line in existing_lines:
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        k = stripped.partition("=")[0].strip()
        if k in env:
            new_lines.append(f"{k}={env[k]}")
            written_keys.add(k)
        else:
            new_lines.append(line)

    # 追加新增的 key
    for k, v in env.items():
        if k not in written_keys:
            new_lines.append(f"{k}={v}")

    p.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _test_deepseek(api_key: str, api_base: str, model: str) -> tuple[bool, str]:
    try:
        resp = httpx.post(
            f"{api_base.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": "回复OK"}], "max_tokens": 10},
            timeout=15.0,
        )
        resp.raise_for_status()
        return True, "✅ 连接成功"
    except Exception as e:
        return False, f"❌ 失败：{e}"


def _test_doubao(api_key: str, api_base: str, model: str) -> tuple[bool, str]:
    try:
        resp = httpx.post(
            f"{api_base.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": "回复OK"}], "max_tokens": 10},
            timeout=15.0,
        )
        resp.raise_for_status()
        return True, "✅ 连接成功"
    except Exception as e:
        return False, f"❌ 失败：{e}"


def render():
    st.header("⚙️ API 配置")

    env = _load_env()

    # ── DeepSeek 配置 ─────────────────────────────────────────────────────────
    st.subheader("规范解析模型（DeepSeek）")
    with st.form("deepseek_form"):
        ds_key = st.text_input(
            "API Key", value=env.get("DEEPSEEK_API_KEY", ""), type="password", key="ds_key"
        )
        ds_base = st.text_input(
            "API Base", value=env.get("DEEPSEEK_API_BASE", "https://ark.cn-beijing.volces.com/api/v3")
        )
        ds_model = st.text_input(
            "模型名称", value=env.get("DEEPSEEK_MODEL", "deepseek-v3-2-251201")
        )
        col1, col2 = st.columns(2)
        save_ds = col1.form_submit_button("💾 保存", use_container_width=True)
        test_ds = col2.form_submit_button("🔌 测试连接", use_container_width=True)

    if save_ds:
        env["DEEPSEEK_API_KEY"] = ds_key
        env["DEEPSEEK_API_BASE"] = ds_base
        env["DEEPSEEK_MODEL"] = ds_model
        _save_env(env)
        st.success("DeepSeek 配置已保存")

    if test_ds:
        with st.spinner("测试中…"):
            ok, msg = _test_deepseek(ds_key, ds_base, ds_model)
        if ok:
            st.success(msg)
        else:
            st.error(msg)

    st.divider()

    # ── Doubao 多 Key 配置 ────────────────────────────────────────────────────
    st.subheader("海报分析模型（豆包 Doubao）")

    # 读取已有 keys
    if "doubao_keys" not in st.session_state:
        keys = []
        for i in range(10):
            k = env.get(f"OPENAI_API_KEY_{i}", "")
            if k:
                keys.append(k)
        if not keys and env.get("OPENAI_API_KEY"):
            keys.append(env["OPENAI_API_KEY"])
        if not keys:
            keys = [""]
        st.session_state["doubao_keys"] = keys

    doubao_base = st.text_input(
        "API Base",
        value=env.get("OPENAI_API_BASE", "https://ark.cn-beijing.volces.com/api/v3"),
        key="doubao_base",
    )
    doubao_model = st.text_input(
        "模型名称",
        value=env.get("DOUBAO_MODEL", "doubao-seed-2-0-pro-260215"),
        key="doubao_model",
    )

    st.markdown("**API Keys**（支持多 Key 轮询，批量审核时并发使用）")

    keys: list = st.session_state["doubao_keys"]
    to_delete = None

    for i, key_val in enumerate(keys):
        col_label, col_input, col_test, col_del = st.columns([1, 5, 1.5, 1])
        col_label.markdown(f"<br>Key {i+1}", unsafe_allow_html=True)
        new_val = col_input.text_input(
            f"key_{i}", value=key_val, type="password", label_visibility="collapsed", key=f"doubao_key_{i}"
        )
        keys[i] = new_val

        if col_test.button("测试", key=f"test_key_{i}"):
            with st.spinner(f"测试 Key {i+1}…"):
                ok, msg = _test_doubao(new_val, doubao_base, doubao_model)
            if ok:
                st.success(f"Key {i+1}: {msg}")
            else:
                st.error(f"Key {i+1}: {msg}")

        if col_del.button("🗑️", key=f"del_key_{i}"):
            if len(keys) > 1:
                to_delete = i
            else:
                st.warning("至少保留一个 Key")

    if to_delete is not None:
        st.session_state["doubao_keys"].pop(to_delete)
        st.rerun()

    col_add, col_test_all, col_save = st.columns(3)

    if col_add.button("➕ 添加 Key", use_container_width=True):
        st.session_state["doubao_keys"].append("")
        st.rerun()

    if col_test_all.button("🔌 测试全部", use_container_width=True):
        results = []
        for i, k in enumerate(keys):
            ok, msg = _test_doubao(k, doubao_base, doubao_model)
            results.append(f"Key {i+1}: {msg}")
        for r in results:
            if "✅" in r:
                st.success(r)
            else:
                st.error(r)

    if col_save.button("💾 保存 Doubao 配置", use_container_width=True, type="primary"):
        # 清除旧的 indexed keys
        for i in range(10):
            env.pop(f"OPENAI_API_KEY_{i}", None)
        env.pop("OPENAI_API_KEY", None)
        env.pop("OPENAI_API_KEYS", None)

        valid_keys = [k for k in keys if k.strip()]
        for i, k in enumerate(valid_keys):
            env[f"OPENAI_API_KEY_{i}"] = k

        env["OPENAI_API_BASE"] = doubao_base
        env["DOUBAO_MODEL"] = doubao_model
        _save_env(env)

        # 同步到运行时环境变量（当前进程立即生效）
        for i in range(10):
            os.environ.pop(f"OPENAI_API_KEY_{i}", None)
        for i, k in enumerate(valid_keys):
            os.environ[f"OPENAI_API_KEY_{i}"] = k
        os.environ["OPENAI_API_BASE"] = doubao_base
        os.environ["DOUBAO_MODEL"] = doubao_model

        st.success(f"Doubao 配置已保存（{len(valid_keys)} 个 Key）")
        # 重置缓存，下次读取时重新加载
        st.session_state.pop("doubao_keys", None)
        st.rerun()
