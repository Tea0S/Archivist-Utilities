import json
import httpx
from typing import Tuple, Any
from .config import settings

async def post_gas(payload: dict, url: str | None = None, timeout: float = 20.0) -> Tuple[bool, Any]:
    """
    POST JSON to Apps Script. Returns (ok, data_or_text).
    Follows GAS 302 redirects automatically.
    """
    target = url or settings.WEBHOOK_URL
    body = dict(payload)
    body["secret"] = settings.GSCRIPT_SECRET
    headers = {
        "Content-Type": "application/json",
        "X-Secret": settings.GSCRIPT_SECRET,
    }
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as x:
        r = await x.post(target, json=body, headers=headers)
        # Try JSON first
        try:
            return True, r.json()
        except Exception:
            txt = (r.text or "").strip()
            if txt.startswith("{") or txt.startswith("["):
                try:
                    return True, json.loads(txt)
                except Exception:
                    pass
            return (r.status_code < 400), txt