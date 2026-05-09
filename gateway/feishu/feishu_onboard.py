"""飞书/Lark 引导接入 —— 扫码创建应用并验证凭证。

提供基于二维码的注册流程，用于自动创建
具有正确权限的飞书/Lark bot 应用。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_ONBOARD_ACCOUNTS_URLS = {
    "feishu": "https://accounts.feishu.cn",
    "lark": "https://accounts.larksuite.com",
}

_ONBOARD_OPEN_URLS = {
    "feishu": "https://open.feishu.cn",
    "lark": "https://open.larksuite.com",
}

_REGISTRATION_PATH = "/oauth/v1/app/registration"
_ONBOARD_REQUEST_TIMEOUT_S = 10


# ---------------------------------------------------------------------------
# 注册流程
# ---------------------------------------------------------------------------


def _accounts_base_url(domain: str) -> str:
    """
    通过用户选择的domain来判断是feishu还是lark(飞书国际版)的域名
    :param domain:
    :return:
    """

    return _ONBOARD_ACCOUNTS_URLS.get(domain, _ONBOARD_ACCOUNTS_URLS["feishu"])


def _onboard_open_base_url(domain: str) -> str:
    return _ONBOARD_OPEN_URLS.get(domain, _ONBOARD_OPEN_URLS["feishu"])


def _post_registration(base_url: str, body: dict[str, str]) -> dict:
    """向注册接口 POST 表单编码数据，并返回解析后的 JSON。

    注册接口即使在 4xx 情况下也会返回 JSON（例如轮询时返回
    authorization_pending 作为 400）。因此无论 HTTP 状态码如何，
    都始终解析响应体。
    """
    url = f"{base_url}{_REGISTRATION_PATH}"
    data = urlencode(body).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlopen(req, timeout=_ONBOARD_REQUEST_TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        body_bytes = exc.read()
        if body_bytes:
            try:
                return json.loads(body_bytes.decode("utf-8"))
            except (ValueError, json.JSONDecodeError):
                raise exc from None
        raise


def _init_registration(domain: str = "feishu") -> None:
    """验证当前环境是否支持 client_secret 认证。

    如果不支持，则抛出 RuntimeError。
    """
    base_url = _accounts_base_url(domain)
    res = _post_registration(base_url, {"action": "init"})
    methods = res.get("supported_auth_methods") or []
    if "client_secret" not in methods:
        raise RuntimeError(
            f"Feishu / Lark registration environment does not support client_secret auth. "
            f"Supported: {methods}"
        )


def _begin_registration(domain: str = "feishu") -> dict:
    """启动设备码流程。返回 device_code、qr_url、user_code、interval、expire_in。"""
    base_url = _accounts_base_url(domain)
    res = _post_registration(base_url, {
        "action": "begin",
        "archetype": "PersonalAgent",
        "auth_method": "client_secret",
        "request_user_info": "open_id",
    })

    device_code = res.get("device_code")
    if not device_code:
        raise RuntimeError("Feishu / Lark registration did not return a device_code")

    qr_url = res.get("verification_uri_complete", "")
    if "?" in qr_url:
        qr_url += "&from=bobby&tp=bobby"
    else:
        qr_url += "?from=bobby&tp=bobby"

    return {
        "device_code": device_code,
        "qr_url": qr_url,
        "user_code": res.get("user_code", ""),
        "interval": res.get("interval") or 5,
        "expire_in": res.get("expire_in") or 600,
    }


def _poll_registration(
    *,
    device_code: str,
    interval: int,
    expire_in: int,
    domain: str = "feishu",
) -> Optional[dict]:
    """轮询直到用户扫描二维码，或发生超时/拒绝。

    成功时返回包含 app_id、app_secret、domain、open_id 的 dict。
    失败时返回 None。
    """
    deadline = time.time() + expire_in
    current_domain = domain
    domain_switched = False
    poll_count = 0

    while time.time() < deadline:
        base_url = _accounts_base_url(current_domain)
        try:
            res = _post_registration(base_url, {
                "action": "poll",
                "device_code": device_code,
                "tp": "ob_app",
            })
        except (URLError, OSError, json.JSONDecodeError):
            time.sleep(interval)
            continue

        poll_count += 1
        if poll_count == 1:
            print("  Fetching configuration results...", end="", flush=True)
        elif poll_count % 6 == 0:
            print(".", end="", flush=True)

        # 自动检测域名
        user_info = res.get("user_info") or {}
        tenant_brand = user_info.get("tenant_brand")
        if tenant_brand == "lark" and not domain_switched:
            current_domain = "lark"
            domain_switched = True
            # 继续向下执行 —— 服务端可能会在同一个响应中返回凭证。

        # 成功
        if res.get("client_id") and res.get("client_secret"):
            if poll_count > 0:
                print()  # 在 "Fetching configuration results..." 点号后换行
            return {
                "app_id": res["client_id"],
                "app_secret": res["client_secret"],
                "domain": current_domain,
                "open_id": user_info.get("open_id"),
            }

        # 终止性错误
        error = res.get("error", "")
        if error in ("access_denied", "expired_token"):
            if poll_count > 0:
                print()
            logger.warning("[Feishu onboard] Registration %s", error)
            return None

        # authorization_pending 或未知状态 —— 继续轮询
        time.sleep(interval)

    if poll_count > 0:
        print()
    logger.warning("[Feishu onboard] Poll timed out after %ds", expire_in)
    return None


try:
    import qrcode as _qrcode_mod
except (ImportError, TypeError):
    _qrcode_mod = None  # type: ignore[assignment]


def _render_qr(url: str) -> bool:
    """尝试在终端中渲染二维码。成功则返回 True。"""
    if _qrcode_mod is None:
        return False
    try:
        qr = _qrcode_mod.QRCode()
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
        return True
    except Exception:
        return False


def probe_bot(app_id: str, app_secret: str, domain: str) -> Optional[dict]:
    """通过 /open-apis/bot/v3/info 验证 bot 连通性。

    如果可用，则使用 lark_oapi SDK；否则回退到原始 HTTP。
    成功时返回 {"bot_name": ..., "bot_open_id": ...}，失败时返回 None。

    注意：这里的 ``bot_open_id`` 是 bot 的应用范围 open_id ——
    与飞书在 @提及事件载荷中放入的 ID 相同。它不是 app_id。
    """
    try:
        import lark_oapi as lark
        from lark_oapi.api.application.v6 import GetApplicationRequest
        from lark_oapi.core import HttpMethod, AccessTokenType
        from lark_oapi.core.model import BaseRequest
    except ImportError:
        return _probe_bot_http(app_id, app_secret, domain)

    return _probe_bot_sdk(app_id, app_secret, domain)


def _probe_bot_sdk(app_id: str, app_secret: str, domain: str) -> Optional[dict]:
    """使用 lark_oapi SDK 探测 bot 信息。"""
    try:
        import lark_oapi as lark
        from lark_oapi.core import HttpMethod, AccessTokenType, FEISHU_DOMAIN, LARK_DOMAIN
    except ImportError:
        return None

    sdk_domain = LARK_DOMAIN if domain == "lark" else FEISHU_DOMAIN
    try:
        client = (
            lark.Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .domain(sdk_domain)
            .log_level(lark.LogLevel.WARNING)
            .build()
        )
        req = (
            BaseRequest.builder()
            .http_method(HttpMethod.GET)
            .uri("/open-apis/bot/v3/info")
            .token_types({AccessTokenType.TENANT})
            .build()
        )
        resp = client.request(req)
        content = getattr(getattr(resp, "raw", None), "content", None)
        if content is None:
            return None
        return _parse_bot_response(json.loads(content))
    except Exception as exc:
        logger.debug("[Feishu onboard] SDK probe failed: %s", exc)
        return None


def _parse_bot_response(data: dict) -> Optional[dict]:
    """解析 /bot/v3/info 响应。"""
    if data.get("code") != 0:
        return None
    bot = data.get("bot") or data.get("data", {}).get("bot") or {}
    return {
        "bot_name": bot.get("app_name") or bot.get("bot_name"),
        "bot_open_id": bot.get("open_id"),
    }


def _probe_bot_http(app_id: str, app_secret: str, domain: str) -> Optional[dict]:
    """使用原始 HTTP 进行回退探测（当未安装 lark_oapi 时）。"""
    base_url = _onboard_open_base_url(domain)
    try:
        token_data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8")
        token_req = Request(
            f"{base_url}/open-apis/auth/v3/tenant_access_token/internal",
            data=token_data,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(token_req, timeout=_ONBOARD_REQUEST_TIMEOUT_S) as resp:
            token_res = json.loads(resp.read().decode("utf-8"))

        access_token = token_res.get("tenant_access_token")
        if not access_token:
            return None

        bot_req = Request(
            f"{base_url}/open-apis/bot/v3/info",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        )
        with urlopen(bot_req, timeout=_ONBOARD_REQUEST_TIMEOUT_S) as resp:
            bot_res = json.loads(resp.read().decode("utf-8"))

        return _parse_bot_response(bot_res)
    except (URLError, OSError, KeyError, json.JSONDecodeError) as exc:
        logger.debug("[Feishu onboard] HTTP probe failed: %s", exc)
        return None


def qr_register(
    *,
    initial_domain: str = "feishu",
    timeout_seconds: int = 600,
) -> Optional[dict]:
    """运行飞书 / Lark 扫码创建二维码注册流程。

    成功时返回::

        {
            "app_id": str,
            "app_secret": str,
            "domain": "feishu" | "lark",
            "open_id": str | None,
            "bot_name": str | None,
            "bot_open_id": str | None,
        }

    在预期失败场景下返回 None（网络问题、授权被拒绝、超时）。
    非预期错误（bug、协议回归）会继续向调用方抛出。
    """
    try:
        return _qr_register_inner(initial_domain=initial_domain, timeout_seconds=timeout_seconds)
    except (RuntimeError, URLError, OSError, json.JSONDecodeError) as exc:
        logger.warning("[Feishu onboard] Registration failed: %s", exc)
        return None


def _qr_register_inner(
    *,
    initial_domain: str,
    timeout_seconds: int,
) -> Optional[dict]:
    """执行 init → begin → poll → probe。网络/协议错误会抛出。"""
    print("  Connecting to Feishu / Lark...", end="", flush=True)
    _init_registration(initial_domain)
    begin = _begin_registration(initial_domain)
    print(" done.")

    print()
    qr_url = begin["qr_url"]
    if _render_qr(qr_url):
        print("  请直接使用飞书 / Lark 扫描上方二维码。")
        print()
    else:
        print(f"  Open this URL in Feishu / Lark on your phone:\n\n  {qr_url}\n")
        print("  Tip: pip install qrcode to display a scannable QR code here next time")

    print("  Waiting for you to scan the QR code...")

    result = _poll_registration(
        device_code=begin["device_code"],
        interval=begin["interval"],
        expire_in=min(begin["expire_in"], timeout_seconds),
        domain=initial_domain,
    )
    if not result:
        return None

    # 探测 bot —— 尽力而为，不因为探测失败导致注册失败
    bot_info = probe_bot(result["app_id"], result["app_secret"], result["domain"])
    if bot_info:
        result["bot_name"] = bot_info.get("bot_name")
        result["bot_open_id"] = bot_info.get("bot_open_id")
    else:
        result["bot_name"] = None
        result["bot_open_id"] = None

    return result