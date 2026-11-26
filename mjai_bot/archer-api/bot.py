"""Archer API mjai adapter for ordinary three/four-player riichi mahjong."""
from __future__ import annotations

from collections import Counter, OrderedDict
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import tomllib

from archer_client import ArcherClient, ArcherError, compact

VERSION = "0.4.6"
WEIGHT_TEMPERATURE = {3: 1.0, 4: 20.0}
ROOT = Path(__file__).resolve().parent
FIELDS = {
    "start_kyoku": ("bakaze", "dora_marker", "kyoku", "honba", "kyotaku", "oya", "scores", "tehais"),
    "kita": ("actor",),
    "tsumo": ("actor", "pai"), "dahai": ("actor", "pai", "tsumogiri"),
    "chi": ("actor", "target", "pai", "consumed"), "pon": ("actor", "target", "pai", "consumed"),
    "daiminkan": ("actor", "target", "pai", "consumed"),
    "kakan": ("actor", "pai", "consumed"), "ankan": ("actor", "consumed"),
    "dora": ("dora_marker",), "reach": ("actor",), "reach_accepted": ("actor",),
}
LABELS = {"dahai": "打牌", "reach": "立直", "chi": "吃", "pon": "碰", "kan": "杠",
          "daiminkan": "明杠", "ankan": "暗杠", "kakan": "加杠",
          "nuki": "拔北", "kita": "拔北", "hora": "和牌", "ryukyoku": "九种九牌", "none": "跳过"}
TILES = {str(n) + suit for suit in "mps" for n in range(1, 10)} | {"5mr", "5pr", "5sr"} | set("ESWNPFC")


def settings_from_disk():
    with (ROOT / "manifest.toml").open("rb") as stream:
        manifest = tomllib.load(stream)
    values = {key: spec["default"] for key, spec in manifest["settings"].items()}
    resolved = os.environ.get("AKAGI_BOT_CONFIG")
    if resolved:
        with open(resolved, "r", encoding="utf-8-sig") as stream:
            values.update(json.load(stream))
    elif (ROOT / "settings.toml").exists():
        with (ROOT / "settings.toml").open("rb") as stream:
            values.update(tomllib.load(stream))
    return values


def notify(level, title, body):
    print("@@AKAGI_NOTIFY@@ " + json.dumps(
        {"level": level, "title": title, "body": body, "id": "archer-api-status", "sticky": False},
        ensure_ascii=True, separators=(",", ":")), file=sys.stderr, flush=True)


def no_action():
    return {"type": "none"}


def finite_number(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def weight_percentages(weights):
    """Largest-remainder rounding keeps the displayed tenths at exactly 100%."""
    total = math.fsum(weights)
    exact = [weight / total * 1000 for weight in weights]
    units = [math.floor(value) for value in exact]
    order = sorted(range(len(units)), key=lambda i: (-(exact[i] - units[i]), i))
    for index in order[:1000 - sum(units)]:
        units[index] += 1
    return [unit / 10 for unit in units]


class ArcherBot:
    def __init__(self, settings, seat=0, client=None, notifier=notify):
        self.settings = settings
        self.seat = seat
        self.client = client
        self.notifier = notifier
        self.model = self.model_for(4)
        self.client_error = None
        if self.client is None:
            try:
                self.client = ArcherClient(settings)
                self.client.prepare_async()
            except (ArcherError, ValueError, TypeError) as exc:
                self.client_error = exc if isinstance(exc, ArcherError) else ArcherError("configuration", "连接配置格式不正确。")
        self.num_players = 4
        self.events = []
        self.hand = Counter()
        self.hand_active = False
        self.riichi = False
        self.pending_next = None
        self.cache = OrderedDict()
        self.blocked = None
        self.cooldown_until = 0.0
        self.last_notice = None
        self.calls = 0
        self.billed = 0
        self.balance = None
        self.uncertain = 0
        self.latest_usage = None
        self.skipped = 0

    def model_for(self, players):
        key = "model_3p" if players == 3 else "model"
        return str(self.settings.get(key, "")).strip()

    def reset_hand(self):
        self.events = []
        self.hand = Counter()
        self.hand_active = False
        self.riichi = False
        self.pending_next = None
        self.cache.clear()

    def status(self, text, *, error=False, label_key="no_advice"):
        items = [{"label": text, "label_key": label_key, "value": "", "color": "#ef4444" if error else "#94a3b8"}]
        return {"type": "none", "meta": {"archer": self.meta_state(), "show": {
            "title": "Archer · " + (self.model or "API"), "items": items}}}

    def meta_state(self):
        return {"version": VERSION, "model": self.model, "players": self.num_players, "calls": self.calls, "billed_tokens": self.billed,
                "balance": self.balance, "uncertain_requests": self.uncertain,
                "last_usage": self.latest_usage, "skipped_requests": self.skipped, "timing": getattr(self.client, "last_timing", {})}

    def error(self, exc):
        if exc.code != self.last_notice:
            self.notifier("error", "Archer · 暂无建议", str(exc))
            self.last_notice = exc.code
        return self.status(str(exc) + " 请手动判断。", error=True)

    def normalise(self, event):
        kind = event.get("type")
        if kind not in FIELDS:
            raise ArcherError("unsupported_event", "出现未支持的牌局事件，本小局暂停查询。")
        required = FIELDS[kind]
        if any(key not in event for key in required):
            raise ArcherError("invalid_events", "牌局事件缺少必要字段，本小局暂停查询。")
        out = {"type": kind, **{key: deepcopy(event[key]) for key in required}}
        if kind == "start_kyoku":
            hands, scores = out["tehais"], out["scores"]
            if len(hands) != self.num_players or len(scores) != self.num_players or not 0 <= self.seat < self.num_players:
                raise ArcherError("unsupported_mode", "牌局人数或座位信息不正确。")
            if len(hands[self.seat]) != 13 or any(tile not in TILES for tile in hands[self.seat]):
                raise ArcherError("invalid_events", "没有完整的自家起手牌，请从新小局开始捕获。")
            out["tehais"] = [hand if index == self.seat else ["?"] * 13 for index, hand in enumerate(hands)]
        elif kind == "kita":
            out["type"] = "nuki"
            out["pai"] = "N"
        elif kind == "tsumo" and out["actor"] != self.seat:
            out["pai"] = "?"
        return out

    def ingest(self, event):
        if not isinstance(event, dict):
            raise ArcherError("invalid_events", "牌局事件格式不正确。")
        kind = event.get("type")
        if kind == "start_game":
            self.reset_hand()
            self.num_players = event.get("num_players", 4)
            self.model = self.model_for(self.num_players)
            if "id" in event:
                if type(event["id"]) is not int or event["id"] not in range(4):
                    raise ArcherError("invalid_events", "座位信息不正确。")
                self.seat = event["id"]
            self.calls, self.billed, self.balance, self.uncertain = 0, 0, None, 0
            self.skipped = 0
            self.latest_usage = None
            self.blocked = None
            return
        if kind == "start_kyoku":
            self.reset_hand()
            self.num_players = event.get("num_players", self.num_players)
            self.model = self.model_for(self.num_players)
            if self.num_players not in (3, 4):
                raise ArcherError("unsupported_mode", "当前仅支持普通三麻或四麻。")
            out = self.normalise(event)
            self.events = [out]
            self.hand = Counter(out["tehais"][self.seat])
            self.hand_active = True
            return
        if kind in ("hora", "ryukyoku", "end_kyoku", "end_game"):
            self.hand_active = False
            self.riichi = False
            self.pending_next = None
            return
        if kind == "none":
            return
        if not self.hand_active:
            return
        out = self.normalise(event)
        self.events.append(out)
        if len(self.events) > 400:
            raise ArcherError("too_large", "本小局事件超过 400 条，暂停到下一小局。")
        if out.get("actor") != self.seat:
            return
        if kind in ("reach", "reach_accepted"):
            self.riichi = True
        if kind == "tsumo":
            if out["pai"] not in TILES:
                raise ArcherError("invalid_events", "自家摸牌信息缺失。")
            self.hand[out["pai"]] += 1
        elif kind == "dahai":
            self.remove_tiles([out["pai"]])
            self.pending_next = None
        elif kind in ("chi", "pon", "daiminkan", "ankan"):
            self.remove_tiles(out["consumed"])
        elif kind == "kakan":
            self.remove_tiles([out["pai"]])
        elif kind == "kita":
            self.remove_tiles(["N"])

    def remove_tiles(self, tiles):
        missing = Counter(tiles) - self.hand
        if missing:
            raise ArcherError("invalid_events", "牌局手牌与事件不一致，请等待下一小局。")
        self.hand.subtract(tiles)
        self.hand += Counter()

    def decision_point(self, last):
        kind, actor = last.get("type"), last.get("actor")
        return (kind == "tsumo" and actor == self.seat
                or kind in ("chi", "pon") and actor == self.seat
                or kind in ("dahai", "kakan") and actor != self.seat)

    def forced_reply(self, last):
        """Only skip when the host has a complete, event-matched legal set."""
        choices = last.get("_ap_legal_actions")
        if not isinstance(choices, list) or any(
                not isinstance(a, dict) or a.get("type") not in LABELS for a in choices):
            return None
        types = {a["type"] for a in choices}
        if last.get("type") in ("dahai", "kakan") and last.get("actor") != self.seat:
            if types <= {"none"}:
                self.skipped += 1
                return {**no_action(), "meta": {"archer": {**self.meta_state(), "skip_reason": "no_legal_claim"}}}
        if (self.riichi and last.get("type") == "tsumo" and last.get("actor") == self.seat
                and types == {"dahai"} and last.get("pai") in TILES
                and all(a.get("pai") == last["pai"] for a in choices)):
            self.skipped += 1
            return {"type": "dahai", "actor": self.seat, "pai": last["pai"], "tsumogiri": True,
                    "meta": {"archer": {**self.meta_state(), "skip_reason": "riichi_tsumogiri"},
                             "show": {"title": "Archer · " + self.model, "items": [{
                                 "label": "摸切", "label_key": "tsumogiri", "type": "dahai", "pais": [last["pai"]],
                                 "value": "100.0%", "weight": 1.0, "weight_percent": 100.0,
                                 "color": "#6ee7b7"}]}}}
        return None

    def chi_tiles(self, candidate, action):
        discard = next((e for e in reversed(self.events) if e["type"] == "dahai"), None)
        if not discard or discard.get("actor") == self.seat:
            return None
        tile = discard["pai"]
        if len(tile) < 2 or tile[1] not in "mps":
            return None
        kind = candidate.get("kind")
        if kind not in ("low", "mid", "high"):
            return None
        rank, suit = int(tile[0]), tile[1]
        low = rank - {"low": 0, "mid": 1, "high": 2}[kind]
        if not 1 <= low <= 7:
            return None
        # Use the selected action's exact red-five choice where it matches.
        actual = action.get("consumed", []) if action["type"] == "chi" else []
        ranks = [r for r in range(low, low + 3) if r != rank]
        if sorted(p[:2] for p in actual) == sorted(str(r) + suit for r in ranks):
            held = actual
        else:
            held = []
            for r in ranks:
                normal = str(r) + suit
                selected = normal if self.hand[normal] else normal + "r"
                if selected not in TILES or not self.hand[selected]:
                    return None
                held.append(selected)
        return sorted([tile, *held], key=lambda p: int(p[0]))

    def matching_pon(self, tile):
        """Find this seat's still-unupgraded pon of this exact tile kind."""
        if tile not in TILES:
            return None
        kind = tile.removesuffix("r")
        for event in reversed(self.events):
            if event.get("actor") != self.seat:
                continue
            called = event.get("pai")
            if called not in TILES or called.removesuffix("r") != kind:
                continue
            if event["type"] == "kakan":
                return None
            if event["type"] == "pon":
                return [called, *event["consumed"]]
        return None

    def kakan_candidate_tile(self, candidate):
        """Resolve each compact kan candidate independently; never use row order."""
        if candidate["type"] not in ("kan", "kakan"):
            return None
        tile = candidate.get("pai")
        if tile not in TILES:
            consumed = candidate.get("consumed")
            if (not isinstance(consumed, list) or len(consumed) != 3
                    or any(p not in TILES for p in consumed)
                    or len({p.removesuffix("r") for p in consumed}) != 1):
                return None
            tile = consumed[0]
        if self.matching_pon(tile) is None:
            return None
        held = [p for p, count in self.hand.items()
                if count > 0 and p.removesuffix("r") == tile.removesuffix("r")]
        # A valid upgrade has exactly one fourth tile. Its real red status wins
        # over a score candidate that names only the tile kind.
        return held[0] if len(held) == 1 else None

    def validate_action(self, action, next_action):
        if not isinstance(action, dict):
            raise ArcherError("invalid_response", "引擎没有返回有效动作。")
        kind = action.get("type")
        if kind not in LABELS or kind == "kan":
            raise ArcherError("invalid_response", "引擎返回了未支持的动作。")
        if kind in ("nuki", "kita"):
            if self.num_players != 3 or action.get("actor") != self.seat or self.hand["N"] <= 0:
                raise ArcherError("invalid_response", "拔北建议与当前手牌不一致。")
            return {"type": "kita", "actor": self.seat, "pai": "N"}
        if kind == "none":
            return no_action()
        # MJAI nine-terminals abortive draws have no actor field.
        # Check it if a server includes it, then emit AP's canonical event.
        if kind == "ryukyoku":
            if "actor" in action and (type(action["actor"]) is not int or action["actor"] != self.seat):
                raise ArcherError("invalid_response", "引擎返回的座位与当前座位不一致。")
            return {"type": "ryukyoku"}
        if action.get("actor") != self.seat:
            raise ArcherError("invalid_response", "引擎返回的座位与当前座位不一致。")
        if kind == "reach":
            if not isinstance(next_action, dict) or next_action.get("type") != "dahai":
                raise ArcherError("invalid_response", "立直建议缺少宣言牌。")
            discard = self.validate_action(next_action, None)
            self.pending_next = discard
            return {"type": "reach", "actor": self.seat, "pai": discard["pai"]}
        fields = {
            "dahai": ("actor", "pai", "tsumogiri"),
            "chi": ("actor", "target", "pai", "consumed"),
            "pon": ("actor", "target", "pai", "consumed"),
            "daiminkan": ("actor", "target", "pai", "consumed"),
            "ankan": ("actor", "consumed"), "kakan": ("actor", "pai", "consumed"),
            "hora": ("actor", "target"),
        }[kind]
        if any(key not in action for key in fields):
            raise ArcherError("invalid_response", "引擎动作缺少必要字段。")
        out = {"type": kind, **{key: deepcopy(action[key]) for key in fields}}
        if "pai" in out and out["pai"] not in TILES:
            raise ArcherError("invalid_response", "引擎返回了无效牌名。")
        if "target" in out and (type(out["target"]) is not int or out["target"] not in range(self.num_players)):
            raise ArcherError("invalid_response", "引擎返回了无效目标座位。")
        if kind == "dahai":
            if type(out["tsumogiri"]) is not bool or self.hand[out["pai"]] <= 0:
                raise ArcherError("invalid_response", "引擎建议打出的牌不在当前手牌中。")
        if "consumed" in out:
            required = {"chi": 2, "pon": 2, "daiminkan": 3, "ankan": 4, "kakan": 3}[kind]
            consumed = out["consumed"]
            if not isinstance(consumed, list) or len(consumed) != required or any(p not in TILES for p in consumed):
                raise ArcherError("invalid_response", "引擎副露数据不完整。")
            held = [out["pai"]] if kind == "kakan" else consumed
            if Counter(held) - self.hand:
                raise ArcherError("invalid_response", "引擎副露建议与当前手牌不一致。")
            if kind == "kakan":
                pon = self.matching_pon(out["pai"])
                if pon is None or Counter(consumed) != Counter(pon):
                    raise ArcherError("invalid_response", "加杠建议与当前碰牌不一致。")
        if kind == "hora" and action.get("pai") in TILES:
            out["pai"] = action["pai"]
        return out

    def record_usage(self, response):
        usage = response.get("usage")
        required = ("input_tokens", "output_tokens", "billed_tokens", "balance")
        if not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0 for k in required):
            raise ArcherError("invalid_response", "引擎返回的计费信息不完整，请检查服务器余额。")
        self.latest_usage = {key: usage[key] for key in required}
        self.billed += usage["billed_tokens"]
        self.balance = usage["balance"]

    def reply(self, response):
        self.record_usage(response)
        action = response.get("action")
        if action is None:
            return self.status("本次接口未返回建议，请手动判断。")
        action = self.validate_action(action, response.get("next"))
        candidates = response.get("candidates")
        if not isinstance(candidates, list):
            raise ArcherError("invalid_response", "候选评分格式不正确。")
        rows = []
        ranked = [c for c in candidates if isinstance(c, dict) and c.get("type") in LABELS and finite_number(c.get("q"))]
        ranked.sort(key=lambda c: c["q"], reverse=True)
        selected = ranked[:int(self.settings.get("top_n", 5))]
        mode = self.settings.get("score_mode", "weights")
        weights = [math.exp((item["q"] - ranked[0]["q"]) / WEIGHT_TEMPERATURE[self.num_players]) for item in selected]
        percentages = weight_percentages(weights) if weights else []
        for index, item in enumerate(selected):
            kind, tile = item["type"], item.get("pai")
            gap = max(0.0, ranked[0]["q"] - item["q"])
            value = f"q {item['q']:.4f}"
            if mode == "relative":
                value = "首选" if gap < 0.00005 else f"落后 {gap:.2f}"
            if mode == "weights":
                value = f"{percentages[index]:.1f}%"
            row = {"label": LABELS[kind], "value": value, "type": "kita" if kind == "nuki" else kind}
            row["label_key"] = row["type"]
            if mode == "relative":
                if gap < 0.00005:
                    row["value_key"] = "top"
                else:
                    row.update(value_key="behind", value_arg=f"{gap:.2f}")
            if mode == "weights":
                row.update(weight=weights[index], weight_percent=percentages[index],
                           color="#6ee7b7" if index == 0 else "#93c5fd")
            if tile in TILES:
                row["pais"] = [tile]
            added = self.kakan_candidate_tile(item)
            if added is not None:
                row.update(label=LABELS["kakan"], label_key="kakan", type="kakan", pais=[added])
            if kind == "chi":
                tiles = self.chi_tiles(item, action)
                if tiles:
                    row["pais"] = tiles
            if kind in ("nuki", "kita"):
                row["pais"] = ["N"]
            if kind == "reach" and action["type"] == "reach":
                row["pais"] = [action["pai"]]
            rows.append(row)
        if not rows:
            row = {"label": LABELS[action["type"]], "value": "", "type": action["type"],
                   "label_key": "kita" if action["type"] == "nuki" else action["type"]}
            if mode == "weights":
                row.update(value="100.0%", weight=1.0, weight_percent=100.0, color="#6ee7b7")
            if action.get("pai") in TILES:
                row["pais"] = [action["pai"]]
            rows.append(row)
        if action["type"] == "reach" and not any(row.get("type") == "reach" for row in rows):
            rows.insert(0, {"label": "立直宣言牌", "label_key": "reach_tile", "pais": [action["pai"]], "value": ""})
        action["meta"] = {"archer": {**self.meta_state(), "candidates": candidates},
                          "show": {"title": "Archer · " + self.model, "items": rows}}
        return action

    def react(self, batch):
        if not isinstance(batch, list):
            return self.error(ArcherError("invalid_events", "输入应为事件数组。"))
        if not batch:
            return no_action()
        try:
            for event in batch:
                self.ingest(event)
        except (ArcherError, KeyError, TypeError, ValueError, IndexError):
            self.hand_active = False
            self.riichi = False
            return self.error(ArcherError("invalid_events", "无法还原当前牌局，请从下一小局开始。"))
        last = batch[-1]
        if not self.hand_active:
            if last.get("type") in ("start_game", "start_kyoku", "end_kyoku", "end_game", "hora", "ryukyoku"):
                return self.status("等待新的三麻或四麻决策", label_key="waiting_decision")
            return no_action()
        if last.get("type") == "reach" and last.get("actor") == self.seat and self.pending_next:
            result = deepcopy(self.pending_next)
            result["meta"] = {"archer": self.meta_state()}
            return result
        if not self.decision_point(last):
            return no_action()
        forced = self.forced_reply(last)
        if forced is not None:
            return forced
        if self.client_error:
            return self.error(self.client_error)
        if self.blocked:
            return self.error(self.blocked)
        if not self.model:
            return self.error(ArcherError("configuration", "请在独立配置中选择对应人数的模型。"))
        key = None
        try:
            key = hashlib.sha256(compact({"model": self.model, "seat": self.seat, "events": self.events})).digest()
            if key in self.cache:
                return deepcopy(self.cache[key])
            if time.monotonic() < self.cooldown_until:
                return self.status("服务要求稍后再试，本次暂无建议，请手动判断。", error=True)
            self.calls += 1
            response = self.client.decide(self.model, self.seat, self.events)
            result = self.reply(response)
            self.last_notice = None
            self.cache[key] = deepcopy(result)
            if len(self.cache) > 128:
                self.cache.popitem(last=False)
            return result
        except ArcherError as exc:
            if exc.code in ("invalid_key", "insufficient_balance", "account_disabled", "unknown_model", "configuration"):
                self.blocked = exc
            if exc.code in ("network", "invalid_response"):
                self.uncertain += 1
            # Network errors apply to this state, not a following independent
            # decision. Honor explicit server backoff for rate/load errors.
            delay = exc.retry_after if exc.code == "network" else max(exc.retry_after, 1.0)
            self.cooldown_until = time.monotonic() + delay
            result = self.error(exc)
            if key is not None and exc.code in ("network", "invalid_response"):
                self.cache[key] = deepcopy(result)
                if len(self.cache) > 128:
                    self.cache.popitem(last=False)
            if exc.code == "network":
                prepare = getattr(self.client, "prepare_async", None)
                if callable(prepare):
                    prepare()
            return result
        except (ValueError, TypeError, KeyError, OverflowError):
            self.uncertain += 1
            return self.error(ArcherError("invalid_response", "返回数据无法解析，本次无建议。"))


def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="strict")
    try:
        settings = settings_from_disk()
        seat = int(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("AKAGI_PLAYER_ID", "0"))
        bot = ArcherBot(settings, seat)
    except Exception:
        notify("error", "Archer 配置无法读取", "请打开 Archer API 的配置入口并保存设置。")
        bot = None
    for line in sys.stdin:
        if not line.strip():
            continue
        batch = None
        try:
            batch = json.loads(line)
            result = bot.react(batch) if bot is not None else {
                "type": "none", "meta": {"show": {"title": "Archer API",
                "items": [{"label": "配置无法读取，请手动判断。", "label_key": "no_advice", "value": ""}]}}}
        except Exception:
            # Never leak raw requests, hand contents, settings or credentials to stderr.
            notify("error", "Archer 插件错误", "本次无法给出建议，请手动判断并检查本机配置。")
            result = no_action()
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":"), allow_nan=False), flush=True)
        if isinstance(batch, list) and any(isinstance(e, dict) and e.get("type") == "end_game" for e in batch):
            break


if __name__ == "__main__":
    main()
