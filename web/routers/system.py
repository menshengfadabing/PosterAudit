from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.services.llm_service import llm_service
from src.utils.config import settings
from web.auth import require_admin
from web.deps import verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key), Depends(require_admin)])


def _resolve_env_path() -> Path:
    # 优先用显式配置路径（建议在 docker-compose 里设为 /app/.env.docker）
    configured = (Path((__import__('os').environ.get('LLM_CONFIG_FILE') or '').strip())
                  if (__import__('os').environ.get('LLM_CONFIG_FILE') or '').strip() else None)
    if configured:
        return configured

    app_root = Path(__file__).resolve().parent.parent.parent
    env_docker = app_root / '.env.docker'
    if env_docker.exists():
        return env_docker
    return app_root / '.env'


class LLMConfigItem(BaseModel):
    api_base: str = ''
    model: str = ''
    api_key: str = ''


class MLLMConfigItem(BaseModel):
    api_base: str = ''
    model: str = ''
    api_keys: list[str] = Field(default_factory=list)


class LLMConfigUpdateReq(BaseModel):
    llm: LLMConfigItem
    mllm: MLLMConfigItem


def _mask_key(key: str) -> str:
    key = (key or '').strip()
    if not key:
        return ''
    if len(key) <= 10:
        return '*' * len(key)
    return f'{key[:6]}...{key[-4:]}'


def _clean_keys(keys: list[str]) -> list[str]:
    out: list[str] = []
    for k in keys:
        kk = (k or '').strip()
        if kk:
            out.append(kk)
    return out


def _persist_to_env(
    llm_api_base: str,
    llm_api_key: str,
    llm_model: str,
    mllm_api_base: str,
    mllm_model: str,
    mllm_api_keys: list[str],
) -> Path:
    env_path = _resolve_env_path()
    lines = env_path.read_text(encoding='utf-8').splitlines() if env_path.exists() else []

    managed_exact = {
        'LLM_API_BASE',
        'LLM_API_KEY',
        'LLM_MODEL',
        'MLLM_API_BASE',
        'MLLM_MODEL',
        'MLLM_API_KEY',
        'MLLM_API_KEYS',
    }

    kept: list[str] = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith('#') or '=' not in s:
            kept.append(line)
            continue
        k = s.split('=', 1)[0].strip()
        if k in managed_exact or k.startswith('MLLM_API_KEY_'):
            continue
        kept.append(line)

    kept.extend(
        [
            f'LLM_API_BASE={llm_api_base}',
            f'LLM_API_KEY={llm_api_key}',
            f'LLM_MODEL={llm_model}',
            f'MLLM_API_BASE={mllm_api_base}',
            f'MLLM_MODEL={mllm_model}',
            f"MLLM_API_KEYS={','.join(mllm_api_keys)}",
            f"MLLM_API_KEY={mllm_api_keys[0] if len(mllm_api_keys) == 1 else ''}",
        ]
    )
    for i, k in enumerate(mllm_api_keys):
        kept.append(f'MLLM_API_KEY_{i}={k}')

    env_path.write_text('\n'.join(kept).rstrip() + '\n', encoding='utf-8')
    return env_path


@router.get('/system/llm/config')
def get_llm_config():
    mllm_keys = settings.get_mllm_api_keys()
    llm_key = (settings.llm_api_key or '').strip()

    return {
        'llm': {
            'api_base': settings.llm_api_base,
            'model': settings.llm_model,
            'api_key': llm_key,
            'has_key': bool(llm_key),
            'masked_key': _mask_key(llm_key),
        },
        'mllm': {
            'api_base': settings.mllm_api_base,
            'model': settings.mllm_model,
            'api_keys': mllm_keys,
            'key_count': len(mllm_keys),
            'masked_keys': [_mask_key(k) for k in mllm_keys],
            'has_key': len(mllm_keys) > 0,
        },
        'env_file': str(_resolve_env_path()),
    }


@router.put('/system/llm/config')
def update_llm_config(req: LLMConfigUpdateReq):
    llm_api_base = (req.llm.api_base or '').strip()
    llm_model = (req.llm.model or '').strip()
    llm_api_key = (req.llm.api_key or '').strip()

    mllm_api_base = (req.mllm.api_base or '').strip()
    mllm_model = (req.mllm.model or '').strip()
    mllm_api_keys = _clean_keys(req.mllm.api_keys)

    if llm_api_base:
        settings.llm_api_base = llm_api_base
    if llm_model:
        settings.llm_model = llm_model
    settings.llm_api_key = llm_api_key

    if mllm_api_base:
        settings.mllm_api_base = mllm_api_base
    if mllm_model:
        settings.mllm_model = mllm_model
    settings.mllm_api_keys = ','.join(mllm_api_keys)
    settings.mllm_api_key = mllm_api_keys[0] if len(mllm_api_keys) == 1 else ''

    env_path = _persist_to_env(
        llm_api_base=settings.llm_api_base,
        llm_api_key=settings.llm_api_key,
        llm_model=settings.llm_model,
        mllm_api_base=settings.mllm_api_base,
        mllm_model=settings.mllm_model,
        mllm_api_keys=mllm_api_keys,
    )

    llm_service.set_api_config(api_keys=mllm_api_keys, api_base=settings.mllm_api_base, model=settings.mllm_model)

    return {
        'ok': True,
        'env_file': str(env_path),
        'need_restart': True,
        'message': '配置已写入环境文件。Docker 容器环境变量需重建/重启容器后生效。',
    }


@router.post('/system/llm/test')
def test_llm_connectivity(target: str = 'all'):
    target = (target or 'all').strip().lower()

    payload = {}
    if target in {'all', 'llm', 'text'}:
        ok, msg = llm_service.test_llm_connection()
        payload['llm'] = {'ok': ok, 'message': msg}

    if target in {'all', 'mllm', 'vision'}:
        ok, msg = llm_service.test_mllm_connection()
        payload['mllm'] = {'ok': ok, 'message': msg}

    if not payload:
        return {'ok': False, 'message': f'unsupported target: {target}'}

    payload['ok'] = all(v.get('ok') for _, v in payload.items() if isinstance(v, dict) and 'ok' in v)
    return payload
