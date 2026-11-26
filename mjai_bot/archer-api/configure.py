"""Command-line diagnostics for the Archer plugin."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tomllib

from archer_client import ArcherClient, ArcherError

ROOT = Path(__file__).resolve().parent
SAMPLE_EVENTS = [
    {"type": "start_kyoku", "bakaze": "E", "dora_marker": "2s", "kyoku": 1,
     "honba": 0, "kyotaku": 0, "oya": 0, "scores": [25000] * 4,
     "tehais": [["1m", "2m", "3m", "5m", "5mr", "7p", "8p", "9p", "2s", "3s", "E", "E", "P"]]
               + [["?"] * 13 for _ in range(3)]},
    {"type": "tsumo", "actor": 0, "pai": "4s"},
]


def read_settings():
    with (ROOT / "manifest.toml").open("rb") as stream:
        defaults = {key: spec["default"] for key, spec in tomllib.load(stream)["settings"].items()}
    if (ROOT / "settings.toml").exists():
        with (ROOT / "settings.toml").open("rb") as stream:
            defaults.update(tomllib.load(stream))
    return defaults


def check(settings):
    client = ArcherClient(settings)
    models = client.models(None)
    balance = client.balance()
    names = [model["name"] for model in models if model["players"] == 4]
    names_3p = [model["name"] for model in models if model["players"] == 3]
    configured = str(settings.get("model", "")).strip()
    return {"ok": True, "balance": balance, "models": [m for m in models if m["players"] == 4],
            "models_3p": [m for m in models if m["players"] == 3],
            "selected_3p_valid": settings.get("model_3p", "") in names_3p,
            "selected_model_valid": bool(configured) and configured in names,
            "decision_tested": False}


def readiness(settings, modes=(3, 4)):
    """Free account/model checks; never calls /v1/decide or writes settings."""
    import time
    started = time.perf_counter()
    result = {"state": "error", "message": "", "code": "error", "models": [], "elapsed_ms": 0}
    client = None
    try:
        for players in sorted(set(modes), reverse=True):
            name = str(settings.get("model_3p" if players == 3 else "model", "")).strip()
            if not name:
                result["code"] = f"model_{players}p_missing"
                result["message"] = ("三麻" if players == 3 else "四麻") + "模型尚未配置"
                return result
            result["models"].append({"players": players, "name": name[:80], "available": False})
        client = ArcherClient(settings)
        models = client.models(None)
        balance = client.balance()
        for item in result["models"]:
            item["available"] = any(m["players"] == item["players"] and m["name"] == item["name"] for m in models)
        unavailable = [item for item in result["models"] if not item["available"]]
        if unavailable:
            result["code"] = "unavailable"
            result["message"] = "所选模型不可用，请重新选择"
        elif balance == 0:
            result["code"] = "balance"
            result["message"] = "账户余额不足"
        else:
            result.update(state="ready", code="ready", message="连接正常")
    except ArcherError as exc:
        messages = {"configuration": "请先配置 Archer API 密钥和连接地址",
                    "invalid_key": "API 密钥无效，请重新配置",
                    "account_disabled": "Archer 账号暂时不可用",
                    "network": "无法连接 Archer，请检查网络",
                    "rate_limited": "检查过于频繁，请稍后重试"}
        result["code"] = exc.code if exc.code in messages else "service"
        result["message"] = messages.get(exc.code, "Archer 接口暂时不可用，请稍后重试")
    except Exception:
        result["message"] = "连接检查失败，请检查本机配置"
    finally:
        if client is not None:
            client.close()
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
    return result


def sample_events(players=4):
    from copy import deepcopy
    events = deepcopy(SAMPLE_EVENTS)
    if players == 3:
        events[0]["scores"] = [35000] * 3
        events[0]["tehais"] = events[0]["tehais"][:3]
        events[0]["tehais"][0] = ["1p","2p","3p","5p","5pr","7p","8p","9p","2s","3s","E","E","P"]
    return events


def smoke(settings, players=4):
    client = ArcherClient(settings)
    model = str(settings.get("model_3p" if players == 3 else "model", "")).strip()
    available = [item["name"] for item in client.models(players)]
    if not model or model not in available:
        raise ArcherError("configuration", "请先查询并选择对应人数的有效模型，再保存。")
    if client.balance() <= 0:
        raise ArcherError("insufficient_balance", "Token 余额为 0，未发起付费决策。")
    events = sample_events(players)
    response = client.decide(model, 0, events)
    # Exercise the exact adapter and HUD conversion with the real response.
    from bot import ArcherBot
    class CapturedResponse:
        def decide(self, model, seat, events):
            return response
    adapter = ArcherBot(settings, client=CapturedResponse(), notifier=lambda *args: None)
    result = adapter.react([{"type": "start_game", "id": 0, "num_players": players}] + events)
    meta = result.get("meta", {})
    if result.get("type") == "none" or not meta.get("archer", {}).get("last_usage"):
        raise ArcherError("invalid_response", "接口已返回，但未通过动作与用量验证；请检查本机显示和余额。")
    return {"ok": True, "decision_tested": True, "action": {k: v for k, v in result.items() if k != "meta"},
            "usage": meta["archer"]["last_usage"], "show": meta["show"]}


def write_check(result):
    folder = ROOT / ".akagi"
    folder.mkdir(exist_ok=True)
    (folder / "connection_check.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def diagnose_draft(action, values):
    if not isinstance(values, dict):
        raise ArcherError("configuration", "配置格式不正确。")
    for key, low, high in (("timeout_ms", 500, 4000), ("top_n", 1, 10)):
        if key in values and (type(values[key]) is not int or not low <= values[key] <= high):
            raise ArcherError("configuration", "超时范围 500～4000 毫秒；候选数量范围 1～10。")
    if action == "models":
        client = ArcherClient(values)
        try:
            return {"ok": True, "models": [
                {"name": m["name"], "players": m["players"]} for m in client.models(None)
            ]}
        finally:
            client.close()
    if action == "health":
        result = check(values)
        return {key: result[key] for key in (
            "ok", "balance", "selected_model_valid", "selected_3p_valid"
        )}
    result = smoke(values, 3 if action == "test3" else 4)
    return {"ok": result["ok"], "action": result["action"], "usage": result["usage"]}


def main():
    parser = argparse.ArgumentParser(description="Archer local configuration")
    parser.add_argument("--players", type=int, choices=(3,4), default=4)
    parser.add_argument("--readiness", action="store_true", help="Free pre-game readiness status")
    parser.add_argument("--modes", nargs="+", type=int, choices=(3, 4), default=[3, 4])
    parser.add_argument("--check", action="store_true", help="Read-only model and balance check")
    parser.add_argument("--smoke", action="store_true", help="One paid decision after checking balance")
    parser.add_argument("--diagnose-draft", choices=("models", "health", "test3", "test4"))
    args = parser.parse_args()
    if args.diagnose_draft:
        import sys
        try:
            result = diagnose_draft(args.diagnose_draft, json.loads(sys.stdin.buffer.read(16385)))
        except ArcherError as exc:
            result = {"ok": False, "code": exc.code, "message": str(exc)}
        except Exception:
            result = {"ok": False, "code": "error"}
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        return
    if args.readiness:
        try:
            result = readiness(read_settings(), args.modes)
        except Exception:
            result = {"state": "error", "message": "无法读取 Archer 配置", "models": [], "elapsed_ms": 0}
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        return
    if not args.check and not args.smoke:
        parser.print_help()
        return
    try:
        result = smoke(read_settings(), args.players) if args.smoke else check(read_settings())
        write_check(result)
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except ArcherError as exc:
        result = {"ok": False, "code": exc.code, "message": str(exc), "decision_tested": False}
        write_check(result)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
