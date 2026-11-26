"""Contract tests for the Archer plugin. All requests use a local fixture server."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import http.server
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import unittest
import urllib.request
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "mjai_bot" / "archer-api"
sys.path.insert(0, str(BOT_DIR))
import bot
import configure
from archer_client import ArcherClient, ArcherError

SETTINGS = {"api_url": "https://la.moxcomic.com", "api_key": "test-secret-never-log",
            "model": "fixture-4p", "model_3p": "fixture-3p", "score_mode": "raw", "timeout_ms": 3000, "top_n": 5, "proxy_url": ""}
EVENTS = configure.SAMPLE_EVENTS
START = {"type": "start_game", "id": 0, "num_players": 4}
USAGE = {"input_tokens": 102, "output_tokens": 42, "billed_tokens": 183, "balance": 999817}


def answer(action=None, candidates=None, usage=None, **extra):
    return {"action": action if action is not None else {"type": "dahai", "actor": 0, "pai": "P", "tsumogiri": False},
            "candidates": candidates if candidates is not None else [
                {"type": "dahai", "pai": "P", "q": 8.062}, {"type": "dahai", "pai": "9p", "q": 7.921}],
            "usage": dict(usage or USAGE), **extra}


class FakeClient:
    def __init__(self, responses=None):
        self.responses = list(responses or [answer()])
        self.calls = []

    def decide(self, model, seat, events):
        self.calls.append((model, seat, deepcopy(events)))
        value = self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]
        if isinstance(value, Exception):
            raise value
        return deepcopy(value)


def adapter(responses=None, **settings):
    client = FakeClient(responses)
    notices = []
    instance = bot.ArcherBot({**SETTINGS, **settings}, client=client, notifier=lambda *args: notices.append(args))
    return instance, client, notices


@contextmanager
def fixture_server(responder,persistent=False):
    captured = []
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1" if persistent else "HTTP/1.0"
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.respond(None)

        def do_POST(self):
            self.respond(json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)))))

        def respond(self, body):
            captured.append({"path": self.path, "body": body, "auth": self.headers.get("Authorization"),"port":self.client_address[1]})
            code, value, headers = responder(self.path, body)
            payload = value if isinstance(value, bytes) else json.dumps(value).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            for name, val in headers.items():
                self.send_header(name, val)
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", captured
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def normal_responder(path, body):
    if path == "/v1/models":
        return 200, {"models": [{"name": "fixture-4p", "players": 4}, {"name": "fixture-3p", "players": 3}]}, {}
    if path == "/v1/balance":
        return 200, {"balance": 1000000}, {}
    if path == "/v1/decide":
        return 200, answer(), {}
    return 404, {"error": {"code": "unknown_model"}}, {}


class AdapterTests(unittest.TestCase):
    def test_manifest_and_no_external_dependencies(self):
        manifest = tomllib.loads((BOT_DIR / "manifest.toml").read_text(encoding="utf-8"))
        project = tomllib.loads((BOT_DIR / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(manifest["bot"]["supported_modes"], ["4p","3p"])
        self.assertTrue(manifest["settings"]["api_key"]["secret"])
        self.assertEqual(project["project"]["dependencies"], [])
        self.assertFalse(project["tool"]["uv"]["package"])

    def test_discards_q_and_usage(self):
        instance, client, _ = adapter()
        out = instance.react([START] + deepcopy(EVENTS))
        self.assertEqual(out["type"], "dahai")
        self.assertEqual(out["pai"], "P")
        self.assertEqual(out["meta"]["archer"]["billed_tokens"], 183)
        rows = out["meta"]["show"]["items"]
        self.assertEqual(rows[0]["value"], "q 8.0620")
        self.assertNotIn("prob", rows[0])
        self.assertFalse(any("Token" in json.dumps(row) or row["label"] == "余额" for row in rows))
        self.assertEqual(len(client.calls), 1)

    def test_hidden_information_and_extension_filtering(self):
        instance, client, _ = adapter()
        events = deepcopy(EVENTS)
        events[0]["tehais"][1] = ["1p"] * 13
        events[0]["catch_up"] = 0
        events.insert(1, {"type": "tsumo", "actor": 1, "pai": "2p"})
        instance.react([START] + events)
        sent = client.calls[0][2]
        self.assertEqual(sent[0]["tehais"][1], ["?"] * 13)
        self.assertEqual(sent[1]["pai"], "?")
        self.assertNotIn("catch_up", sent[0])
        self.assertEqual(sent[0]["type"], "start_kyoku")

    def test_round_boundaries_and_no_decision_do_not_call(self):
        instance, client, _ = adapter()
        instance.react([START, deepcopy(EVENTS[0])])
        instance.react([{"type": "dora", "dora_marker": "1p"}])
        instance.react([{"type": "end_kyoku"}])
        instance.react([{"type": "end_game"}])
        self.assertEqual(client.calls, [])

    def test_missing_round_does_not_call(self):
        instance, client, _ = adapter()
        instance.react([START, deepcopy(EVENTS[1])])
        self.assertEqual(client.calls, [])

    def test_three_player_rejects_four_seat_hand_shape(self):
        instance, client, _ = adapter()
        start = {**START, "num_players": 3}
        instance.react([start] + deepcopy(EVENTS))
        self.assertEqual(client.calls, [])
        self.assertFalse(instance.hand_active)

    def test_reach_has_discard_and_followup_uses_no_extra_request(self):
        reach = answer({"type": "reach", "actor": 0}, [{"type": "reach", "q": 8.2}],
                       next={"type": "dahai", "actor": 0, "pai": "9p", "tsumogiri": False})
        instance, client, _ = adapter([reach])
        out = instance.react([START] + deepcopy(EVENTS))
        self.assertEqual((out["type"], out["pai"]), ("reach", "9p"))
        self.assertEqual(out["meta"]["show"]["items"][0]["label"], "立直")
        self.assertEqual(out["meta"]["show"]["items"][0]["pais"], ["9p"])
        followup = instance.react([{"type": "reach", "actor": 0}])
        self.assertEqual((followup["type"], followup["pai"]), ("dahai", "9p"))
        self.assertEqual(len(client.calls), 1)

    def test_reach_missing_next_never_becomes_a_fake_discard(self):
        instance, _, _ = adapter([answer({"type": "reach", "actor": 0})])
        out = instance.react([START] + deepcopy(EVENTS))
        self.assertEqual(out["type"], "none")
        self.assertIn("宣言牌", out["meta"]["show"]["items"][0]["label"])
        self.assertEqual(instance.billed, 183)

    def test_malformed_action_and_wrong_seat_are_rejected(self):
        for action in ({"type": "dahai", "actor": 1, "pai": "P", "tsumogiri": False},
                       {"type": "dahai", "actor": 0, "pai": "9m", "tsumogiri": False}):
            with self.subTest(action=action):
                instance, _, _ = adapter([answer(action)])
                self.assertEqual(instance.react([START] + deepcopy(EVENTS))["type"], "none")

    def test_hand_reset_and_game_usage(self):
        instance, client, _ = adapter()
        instance.react([START] + deepcopy(EVENTS))
        instance.react([{"type": "end_kyoku"}])
        new = deepcopy(EVENTS)
        new[0]["kyoku"] = 2
        instance.react(new)
        self.assertEqual(len(client.calls[1][2]), 2)
        self.assertEqual(instance.billed, 366)

    def test_opponent_discard_and_own_call(self):
        instance, client, _ = adapter([answer({"type": "none"})])
        instance.react([START, deepcopy(EVENTS[0])])
        out = instance.react([{"type": "dahai", "actor": 1, "pai": "E", "tsumogiri": False}])
        self.assertEqual(out["type"], "none")
        # Two East tiles are consumed by our pon; still-queryable hand stays in sync.
        instance.react([{"type": "pon", "actor": 0, "target": 1, "pai": "E", "consumed": ["E", "E"]}])
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(instance.hand["E"], 0)

    def test_null_action_retains_billing(self):
        response = answer()
        response["action"] = None
        instance, _, _ = adapter([response])
        out = instance.react([START] + deepcopy(EVENTS))
        self.assertEqual(out["type"], "none")
        self.assertEqual(out["meta"]["archer"]["billed_tokens"], 183)

    def test_zero_balance_blocks_later_calls(self):
        instance, client, notices = adapter([ArcherError("insufficient_balance", "余额不足")])
        out = instance.react([START] + deepcopy(EVENTS))
        self.assertEqual(out["type"], "none")
        instance.react([{"type": "dahai", "actor": 1, "pai": "E", "tsumogiri": False}])
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(len(notices), 1)

    def test_network_failure_is_not_retried(self):
        instance, client, _ = adapter([ArcherError("network", "超时")])
        out = instance.react([START] + deepcopy(EVENTS))
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(out["meta"]["archer"]["uncertain_requests"], 1)
        # A non-decision event does not retry the timed-out paid state.
        instance.react([{"type": "dora", "dora_marker": "1p"}])
        self.assertEqual(len(client.calls), 1)

    def test_start_game_seat_is_authoritative(self):
        instance, client, _ = adapter()
        events = deepcopy(EVENTS)
        events[0]["tehais"][2], events[0]["tehais"][0] = events[0]["tehais"][0], ["?"] * 13
        events[1]["actor"] = 2
        instance.react([{**START, "id": 2}] + events)
        self.assertEqual(client.calls[0][1], 2)


class TransportTests(unittest.TestCase):
    def test_wire_contract_and_readonly_checks(self):
        with fixture_server(normal_responder) as (url, calls):
            client = ArcherClient({**SETTINGS, "api_url": url})
            self.assertEqual([m["name"] for m in client.models()], ["fixture-4p"])
            self.assertEqual(client.balance(), 1000000)
            response = client.decide("fixture-4p", 0, EVENTS)
            self.assertEqual(response["usage"], USAGE)
            self.assertEqual(calls[-1]["body"]["seat"], 0)
            self.assertNotIn("player_id", calls[-1]["body"])
            self.assertEqual(calls[-1]["auth"], "Bearer " + SETTINGS["api_key"])

    def test_safe_http_error_no_echo_of_server_message(self):
        with fixture_server(lambda p, b: (402, {"error": {"code": "insufficient_balance", "message": SETTINGS["api_key"]}}, {})) as (url, calls):
            with self.assertRaises(ArcherError) as caught:
                ArcherClient({**SETTINGS, "api_url": url}).decide("fixture-4p", 0, EVENTS)
            self.assertEqual(caught.exception.code, "insufficient_balance")
            self.assertNotIn(SETTINGS["api_key"], str(caught.exception))
            self.assertEqual(len(calls), 1)

    def test_cold_start_preserves_retry_after_without_retry(self):
        with fixture_server(lambda p, b: (503, {"error": {"code": "loading"}}, {"Retry-After": "3"})) as (url, calls):
            with self.assertRaises(ArcherError) as caught:
                ArcherClient({**SETTINGS, "api_url": url}).decide("fixture-4p", 0, EVENTS)
            self.assertEqual(caught.exception.retry_after, 3)
            self.assertEqual(len(calls), 1)

    def test_redirect_is_not_followed(self):
        with fixture_server(lambda p, b: (302, {}, {"Location": "/unexpected"})) as (url, calls):
            with self.assertRaises(ArcherError):
                ArcherClient({**SETTINGS, "api_url": url}).models()
            self.assertEqual(len(calls), 1)

    def test_invalid_json_and_non_dict_response(self):
        for payload in (b"<html>no</html>", b"[]"):
            with self.subTest(payload=payload), fixture_server(lambda p, b: (200, payload, {})) as (url, calls):
                with self.assertRaises(ArcherError):
                    ArcherClient({**SETTINGS, "api_url": url}).models()

    def test_unapproved_url_and_proxy_formats(self):
        for patch_values in ({"api_url": "http://example.com"}, {"api_url": "https://example.com/v1/decide"},
                             {"proxy_url": "socks5://127.0.0.1:7890"}):
            with self.subTest(patch_values=patch_values), self.assertRaises(ArcherError):
                ArcherClient({**SETTINGS, **patch_values})

    def test_size_limits_are_local(self):
        with fixture_server(normal_responder) as (url, calls):
            with self.assertRaises(ArcherError):
                ArcherClient({**SETTINGS, "api_url": url}).decide("fixture-4p", 0, EVENTS + [{"type": "dora", "dora_marker": "1m"}] * 401)
            with self.assertRaises(ArcherError):
                ArcherClient({**SETTINGS, "api_url": url}).request("/v1/decide", {"large": "x" * 33000})
            self.assertEqual(calls, [])

    def test_subprocess_jsonl_and_utf8(self):
        with fixture_server(normal_responder) as (url, calls), tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(json.dumps({**SETTINGS, "api_url": url}), encoding="utf-8")
            env = {**os.environ, "AKAGI_BOT_CONFIG": str(config)}
            lines = [json.dumps([START] + EVENTS), json.dumps([{"type": "end_game"}])]
            process = subprocess.run([sys.executable, str(BOT_DIR / "bot.py"), "0"],
                                     input="\n".join(lines) + "\n", text=True, encoding="utf-8",
                                     capture_output=True, env=env, timeout=10, cwd=BOT_DIR)
            self.assertEqual(process.returncode, 0, process.stderr)
            results = [json.loads(line) for line in process.stdout.splitlines()]
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0]["pai"], "P")
            self.assertNotIn(SETTINGS["api_key"], process.stdout + process.stderr)
            self.assertEqual(len(calls), 1)

    def test_real_smoke_path_against_fixture(self):
        with fixture_server(normal_responder) as (url, calls):
            report = configure.smoke({**SETTINGS, "api_url": url})
            self.assertTrue(report["decision_tested"])
            self.assertEqual(report["action"]["pai"], "P")
            self.assertEqual(report["usage"]["billed_tokens"], 183)
            self.assertEqual(len([c for c in calls if c["path"] == "/v1/decide"]), 1)

    def test_zero_balance_check_does_not_spend(self):
        def responder(path, body):
            if path == "/v1/balance":
                return 200, {"balance": 0}, {}
            return normal_responder(path, body)
        with fixture_server(responder) as (url, calls):
            with self.assertRaises(ArcherError):
                configure.smoke({**SETTINGS, "api_url": url})
            self.assertFalse(any(c["path"] == "/v1/decide" for c in calls))

    def test_draft_queries_do_not_save_or_request_inference(self):
        with tempfile.TemporaryDirectory() as directory, fixture_server(normal_responder) as (url, calls):
            with patch.object(configure, "ROOT", Path(directory)):
                settings = {**SETTINGS, "api_url": url}
                models = configure.diagnose_draft("models", settings)
                self.assertTrue(any(model["players"] == 4 for model in models["models"]))
                health = configure.diagnose_draft("health", settings)
                self.assertTrue(health["ok"])
                self.assertTrue(health["selected_model_valid"])
                self.assertFalse((Path(directory) / "settings.toml").exists())
                self.assertEqual([call["path"] for call in calls], ["/v1/models", "/v1/models", "/v1/balance"])


class DualModeTests(unittest.TestCase):
    def test_candidate_weights_total_one_hundred_and_hide_in_game_accounting(self):
        scores = [-4832.255, -4855.101, -4857.379]
        response = answer(candidates=[{"type":"dahai","pai":tile,"q":score}
                                     for tile,score in zip(["P","E","9p"],scores)])
        instance,_,_=adapter([response],score_mode="weights")
        reply=instance.react([START]+deepcopy(EVENTS))
        rows=reply["meta"]["show"]["items"]
        self.assertEqual([row["value"] for row in rows],["62.3%","19.9%","17.8%"])
        self.assertEqual(sum(round(row["weight_percent"]*10) for row in rows),1000)
        self.assertFalse(any("note" in row for row in rows))
        self.assertEqual(reply["meta"]["archer"]["billed_tokens"],183)
        self.assertEqual(reply["meta"]["archer"]["candidates"],response["candidates"])
        self.assertNotIn("Token",json.dumps(reply["meta"]["show"]))
        self.assertNotIn("items",reply["meta"]["archer"])
        status=instance.status("等待新的决策")
        self.assertEqual(len(status["meta"]["show"]["items"]),1)

    def test_weight_rounding_ties_large_scores_and_single_forced_action(self):
        self.assertEqual(bot.weight_percentages([1,1,1]),[33.4,33.3,33.3])
        for values in [[1,0,0],[1]*7,[1e-300,1e-300]]:
            self.assertEqual(sum(round(x*10) for x in bot.weight_percentages(values)),1000)
        for scores in [[1e308,-1e308],[-1e308,-1e308]]:
            response=answer(candidates=[{"type":"dahai","pai":"P","q":q} for q in scores])
            instance,_,_=adapter([response],score_mode="weights")
            rows=instance.react([START]+deepcopy(EVENTS))["meta"]["show"]["items"]
            self.assertEqual(sum(round(row["weight_percent"]*10) for row in rows),1000)
        response=answer();response["candidates"]=[]
        instance,_,_=adapter([response],score_mode="weights")
        rows=instance.react([START]+deepcopy(EVENTS))["meta"]["show"]["items"]
        self.assertEqual(rows[0]["value"],"100.0%")
        response=answer({"type":"reach","actor":0},next={"type":"dahai","actor":0,"pai":"P","tsumogiri":False})
        response["candidates"]=[]
        instance,_,_=adapter([response],score_mode="weights")
        rows=instance.react([START]+deepcopy(EVENTS))["meta"]["show"]["items"]
        self.assertEqual(len(rows),1)
        self.assertEqual((rows[0]["value"],rows[0]["pais"]),("100.0%",["P"]))

    def test_model_selection_changes_with_each_game(self):
        settings={**SETTINGS,"model_3p":"fixture-3p"}
        instance=bot.ArcherBot(settings,client=FakeClient([answer()]),notifier=lambda *args:None)
        instance.react([START]+deepcopy(EVENTS))
        self.assertEqual(instance.model,"fixture-4p")
        three=configure.sample_events(3)
        instance.react([{**START,"num_players":3}]+three)
        self.assertEqual(instance.model,"fixture-3p")
        self.assertEqual(len(instance.events[0]["scores"]),3)
        instance.react([START]+deepcopy(EVENTS))
        self.assertEqual(instance.model,"fixture-4p")

    def test_sanma_north_events_and_reaction_roundtrip(self):
        events=configure.sample_events(3)
        events[0]["tehais"][0][-1]="N"
        client=FakeClient([answer({"type":"nuki","actor":0},[{"type":"nuki","q":-2}])])
        instance=bot.ArcherBot({**SETTINGS,"model_3p":"fixture-3p"},client=client,notifier=lambda *args:None)
        reply=instance.react([{**START,"num_players":3}]+events)
        self.assertEqual(reply["type"],"kita")
        self.assertEqual(reply["pai"],"N")
        # The replacement draw must carry the preceding North event in Archer notation.
        client.responses=[answer({"type":"dahai","actor":0,"pai":"P","tsumogiri":True})]
        instance.react([{"type":"kita","actor":0,"pai":"N"},{"type":"tsumo","actor":0,"pai":"P"}])
        self.assertEqual(client.calls[-1][2][-2],{"type":"nuki","actor":0,"pai":"N"})
        self.assertEqual(instance.hand["N"],0)

    def test_sanma_model_missing_does_not_use_four_player_engine(self):
        instance,client,_=adapter(model_3p="")
        instance.react([{**START,"num_players":3}]+configure.sample_events(3))
        self.assertEqual(client.calls,[])

    def test_relative_scores_preserve_raw_values(self):
        instance,_,_=adapter(score_mode="relative")
        reply=instance.react([START]+deepcopy(EVENTS))
        rows=reply["meta"]["show"]["items"]
        self.assertEqual(rows[0]["value"],"首选")
        self.assertEqual(rows[1]["value"],"落后 0.14")
        self.assertEqual(reply["meta"]["archer"]["candidates"][0]["q"],8.062)
        self.assertNotIn("prob",rows[0])

    def test_direct_connection_reuse(self):
        with fixture_server(normal_responder,persistent=True) as (url,calls):
            client=ArcherClient({**SETTINGS,"api_url":url})
            client.models()
            client.balance()
            self.assertTrue(client.last_timing["connection_reused"])
            self.assertEqual(calls[0]["port"],calls[1]["port"])
            client.close()





class NetworkRecoveryTests(unittest.TestCase):
    def test_next_distinct_decision_is_not_blocked_by_network_cooldown(self):
        instance,client,_=adapter([ArcherError("network","timeout"),answer({"type":"none"})])
        with patch.object(bot.time,"monotonic",return_value=100.0), patch.object(client,"prepare_async",create=True) as prepare:
            first=instance.react([START]+deepcopy(EVENTS))
            self.assertEqual(first["type"],"none");self.assertEqual(len(client.calls),1)
            prepare.assert_called_once()
            second=instance.react([{"type":"dahai","actor":1,"pai":"E","tsumogiri":False}])
            self.assertEqual(len(client.calls),2)
            self.assertEqual(instance.uncertain,1)
            self.assertNotIn("稍后",second["meta"]["show"]["items"][0]["label"])
            self.assertNotEqual(client.calls[0][2],client.calls[1][2])

    def test_same_failed_event_history_is_not_posted_again(self):
        instance,client,_=adapter([ArcherError("network","timeout")])
        first=instance.react([START]+deepcopy(EVENTS))
        # Re-evaluating an unchanged snapshot must return the cached failure,
        # rather than resending a possibly billed inference.
        with patch.object(instance,"ingest"):
            second=instance.react([deepcopy(EVENTS[-1])])
        self.assertEqual(second,first)
        self.assertEqual(len(client.calls),1);self.assertEqual(instance.uncertain,1)

    def test_server_retry_after_still_blocks_following_distinct_decision(self):
        instance,client,_=adapter([ArcherError("busy","busy",status=503,retry_after=3),
                                   answer({"type":"none"})])
        with patch.object(bot.time,"monotonic",return_value=100.0):
            instance.react([START]+deepcopy(EVENTS))
            out=instance.react([{"type":"dahai","actor":1,"pai":"E","tsumogiri":False}])
            self.assertEqual(len(client.calls),1)
            self.assertIn("稍后",out["meta"]["show"]["items"][0]["label"])
        with patch.object(bot.time,"monotonic",return_value=104.0):
            instance.react([{"type":"dahai","actor":2,"pai":"C","tsumogiri":False}])
        self.assertEqual(len(client.calls),2)

    def test_four_second_wait_accepts_slow_response_without_extra_post(self):
        def slow(path,body):
            time.sleep(3.15)
            return normal_responder(path,body)
        with fixture_server(slow,persistent=True) as (url,calls):
            client=ArcherClient({**SETTINGS,"timeout_ms":4000,"api_url":url})
            start=time.monotonic()
            out=client.decide("fixture-4p",0,EVENTS)
            self.assertEqual(out["action"]["type"],"dahai")
            self.assertEqual(len(calls),1)
            self.assertGreater(time.monotonic()-start,3.0)
            self.assertLess(time.monotonic()-start,4.4)
            self.assertEqual(client.last_timing["http_status"],200)
            self.assertEqual(client.last_timing["configured_timeout_ms"],4000)
            client.close()

    def test_timeout_is_descriptive_and_never_reposts(self):
        def slow(path,body):
            time.sleep(0.8)
            return normal_responder(path,body)
        with fixture_server(slow) as (url,calls):
            client=ArcherClient({**SETTINGS,"timeout_ms":500,"api_url":url})
            with self.assertRaises(ArcherError) as caught:client.decide("fixture-4p",0,EVENTS)
            self.assertIn("等待 Archer 响应超时",str(caught.exception))
            self.assertEqual(len(calls),1)
            self.assertEqual(client.last_timing["failure_phase"],"response")

    def test_headers_and_body_share_remaining_budget_with_or_without_keepalive(self):
        import archer_client
        for persistent in (False,True):
            with self.subTest(persistent=persistent):
                captured=[]
                class Handler(http.server.BaseHTTPRequestHandler):
                    protocol_version="HTTP/1.1" if persistent else "HTTP/1.0"
                    def log_message(self,*args):pass
                    def do_POST(self):
                        self.rfile.read(int(self.headers["Content-Length"]));captured.append(1)
                        payload=json.dumps(answer()).encode()
                        time.sleep(0.30)
                        self.send_response(200);self.send_header("Content-Length",str(len(payload)));self.end_headers()
                        try:
                            self.wfile.write(payload[:1]);self.wfile.flush()
                            time.sleep(0.40);self.wfile.write(payload[1:])
                        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
                        finally:self.close_connection=True
                server=http.server.ThreadingHTTPServer(("127.0.0.1",0),Handler);server.daemon_threads=True
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                try:
                    url="http://127.0.0.1:"+str(server.server_port)
                    client=ArcherClient({**SETTINGS,"api_url":url,"timeout_ms":4000})
                    start=time.monotonic()
                    with patch.object(archer_client,"DECISION_BUDGET",0.55):
                        with self.assertRaises(ArcherError):client.decide("fixture-4p",0,EVENTS)
                    self.assertLess(time.monotonic()-start,0.9)
                    self.assertEqual(captured,[1]);self.assertEqual(client.last_timing["http_status"],200)
                finally:
                    server.shutdown();server.server_close();thread.join(timeout=2)

    def test_truncated_http_body_is_not_accepted_as_complete_json(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                payload=json.dumps(answer()).encode()
                self.send_response(200)
                self.send_header("Content-Length",str(len(payload)+10));self.end_headers()
                self.wfile.write(payload);self.close_connection=True
        server=http.server.ThreadingHTTPServer(("127.0.0.1",0),Handler);server.daemon_threads=True
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            client=ArcherClient({**SETTINGS,"api_url":"http://127.0.0.1:"+str(server.server_port)})
            with self.assertRaises(ArcherError):client.decide("fixture-4p",0,EVENTS)
            self.assertEqual(client.last_timing["failure_type"],"IncompleteRead")
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2)

    def test_default_response_wait_is_four_seconds_and_stays_capped(self):
        manifest=tomllib.loads((BOT_DIR/"manifest.toml").read_text("utf8"))
        self.assertEqual(manifest["settings"]["timeout_ms"]["default"],4000)
        values={k:v for k,v in SETTINGS.items() if k!="timeout_ms"}
        self.assertEqual(ArcherClient(values).timeout,4.0)
        self.assertEqual(ArcherClient({**SETTINGS,"timeout_ms":9000}).timeout,4.0)

class MultipleKakanTests(unittest.TestCase):
    def opening(self, players=3, seat=0, count=2):
        # Hold fourth tiles of two/three separate pons. One added tile is red;
        # the other pon already contains red. No five-of-a-kind fixtures.
        groups=[("5p",["5p","5p"],"5pr"),("5s",["5sr","5s"],"5s"),
                ("C",["C","C"],"C")][:count]
        filler=["1p","2p","3p","7s","8s","9s","E"][:13-3*count]
        hand=[t for _,consumed,added in groups for t in [*consumed,added]]+filler
        hands=[["?"]*13 for _ in range(players)];hands[seat]=hand
        target=(seat+1)%players
        events=[{"type":"start_game","id":seat,"num_players":players},
                {"type":"start_kyoku","bakaze":"E","dora_marker":"2s","kyoku":1,
                 "honba":0,"kyotaku":0,"oya":target,"scores":[35000 if players==3 else 25000]*players,
                 "tehais":hands}]
        options=[]
        for i,(called,consumed,added) in enumerate(groups):
            events += [{"type":"tsumo","actor":target,"pai":"?"},
                       {"type":"dahai","actor":target,"pai":called,"tsumogiri":True},
                       {"type":"pon","actor":seat,"target":target,"pai":called,"consumed":consumed},
                       {"type":"dahai","actor":seat,"pai":filler[-1-i],"tsumogiri":False}]
            options.append({"type":"kakan","actor":seat,"pai":added,"consumed":[called,*consumed]})
        for i in range(1,players):
            actor=(seat+i)%players
            events += [{"type":"tsumo","actor":actor,"pai":"?"},
                       {"type":"dahai","actor":actor,"pai":"W","tsumogiri":True}]
        events.append({"type":"tsumo","actor":seat,"pai":"9p","_ap_legal_actions":[
            *deepcopy(options),{"type":"dahai","actor":seat,"pai":"9p","tsumogiri":True}]})
        return events,options

    def test_every_kakan_has_its_own_image_and_selected_pon_for_all_seats(self):
        for players in (3,4):
            for seat in range(players):
                for count in (2,3):
                    for selected in range(count):
                        with self.subTest(players=players,seat=seat,count=count,selected=selected):
                            events,options=self.opening(players,seat,count)
                            # Archer's compact candidates use generic "kan".
                            candidates=[{"type":"kan","pai":opt["pai"],"q":-i/10}
                                        for i,opt in enumerate(options)]
                            instance,client,_=adapter([answer(options[selected],candidates)],score_mode="weights")
                            result=instance.react(events)
                            self.assertEqual({k:v for k,v in result.items() if k!="meta"},options[selected])
                            rows=result["meta"]["show"]["items"]
                            self.assertEqual([r["label"] for r in rows],["加杠"]*count)
                            self.assertEqual([r["pais"] for r in rows],[[a["pai"]] for a in options])
                            self.assertEqual([r["type"] for r in rows],["kakan"]*count)
                            self.assertAlmostEqual(sum(r["weight_percent"] for r in rows),100)
                            self.assertEqual(len(client.calls),1)
                            self.assertNotIn("_ap_legal_actions",str(client.calls[0][2]))

    def test_candidate_order_and_equal_scores_keep_distinct_tiles(self):
        events,options=self.opening(count=3)
        candidates=[{"type":"kakan","pai":a["pai"],"q":-0.5} for a in reversed(options)]
        instance,_,_=adapter([answer(options[0],candidates)],score_mode="weights")
        rows=instance.react(events)["meta"]["show"]["items"]
        self.assertEqual([r["pais"] for r in rows],[[a["pai"]] for a in reversed(options)])
        self.assertAlmostEqual(sum(r["weight_percent"] for r in rows),100)

    def test_consecutive_kakans_only_remove_each_added_tile_and_keep_full_history(self):
        for players in (3,4):
            events,options=self.opening(players=players,count=3)
            instance,client,_=adapter([answer(options[0],[{"type":"kan","pai":a["pai"],"q":-i} for i,a in enumerate(options)])])
            instance.react(events)
            for index,chosen in enumerate(options):
                before=deepcopy(instance.hand)
                instance.ingest(chosen)
                self.assertEqual(instance.hand[chosen["pai"]],before[chosen["pai"]]-1)
                self.assertEqual(sum(instance.hand.values()),sum(before.values())-1)
                for other in options[index+1:]:
                    self.assertEqual(instance.hand[other["pai"]],before[other["pai"]])
                self.assertIsNone(instance.matching_pon(chosen["pai"]))
                if index+1<len(options):
                    # A rinshan draw may leave another pon available to upgrade.
                    draw={"type":"tsumo","actor":0,"pai":"E"}
                    client.responses=[answer(options[index+1],[{"type":"kan","pai":a["pai"],"q":-i}
                                             for i,a in enumerate(options[index+1:])])]
                    out=instance.react([draw])
                    self.assertEqual(out["pai"],options[index+1]["pai"])
                    self.assertEqual(client.calls[-1][2][-2],chosen)
                    self.assertEqual(client.calls[-1][2][-1],draw)
                    self.assertTrue(all(e in client.calls[-1][2] for e in options[:index+1]))

    def test_wrong_consumed_pon_and_wrong_red_composition_are_rejected(self):
        for bad in (["5s","5sr","5s"],["5p","5pr","5p"],["E"]*3):
            with self.subTest(consumed=bad):
                events,options=self.opening()
                action={**options[0],"consumed":bad}
                instance,_,_=adapter([answer(action)])
                result=instance.react(events)
                self.assertEqual(result["type"],"none")
                self.assertIn("碰牌",result["meta"]["show"]["items"][0]["label"])

    def test_fallback_selected_kakan_still_has_its_exact_red_image(self):
        events,options=self.opening()
        instance,_,_=adapter([answer(options[0],[])],score_mode="weights")
        row=instance.react(events)["meta"]["show"]["items"][0]
        self.assertEqual((row["label"],row["pais"],row["value"]),("加杠",["5pr"],"100.0%"))

    def test_red_omitted_in_candidate_recovers_actual_added_tile_from_hand(self):
        events,options=self.opening()
        instance,_,_=adapter([answer(options[0],[{"type":"kan","pai":"5p","q":0},
                                               {"type":"kan","pai":"5s","q":-1}])])
        rows=instance.react(events)["meta"]["show"]["items"]
        self.assertEqual([r["pais"] for r in rows],[["5pr"],["5s"]])

    def test_new_hand_does_not_inherit_previous_pons(self):
        events,options=self.opening()
        instance,_,_=adapter([answer(options[0],[])])
        instance.react(events)
        self.assertIsNotNone(instance.matching_pon("5p"))
        instance.react([{"type":"end_kyoku"},*deepcopy(EVENTS)])
        self.assertIsNone(instance.matching_pon("5p"))

class AbortiveDrawTests(unittest.TestCase):
    def opening(self, players, seat):
        hand=["1m","9m","1p","9p","1s","9s","E","S","W","N","P","F","C"]
        hands=[["?"]*13 for _ in range(players)];hands[seat]=hand
        return [{"type":"start_game","id":seat,"num_players":players},
                {"type":"start_kyoku","bakaze":"E","dora_marker":"2s","kyoku":1,
                 "honba":0,"kyotaku":0,"oya":0,"scores":[35000 if players==3 else 25000]*players,
                 "tehais":hands},{"type":"tsumo","actor":seat,"pai":"9p"}]

    def test_actorless_abortive_draw_reaches_overlay_for_all_seats_and_modes(self):
        for players in (3,4):
            for seat in range(players):
                with self.subTest(players=players,seat=seat):
                    response=answer({"type":"ryukyoku"},[
                        {"type":"ryukyoku","q":0.0},{"type":"dahai","pai":"9p","q":-2.0}])
                    instance,client,_=adapter([response],score_mode="weights")
                    out=instance.react(self.opening(players,seat))
                    self.assertEqual({k:v for k,v in out.items() if k!="meta"},{"type":"ryukyoku"})
                    rows=out["meta"]["show"]["items"]
                    self.assertEqual([r["label"] for r in rows],["九种九牌","打牌"])
                    self.assertAlmostEqual(sum(r["weight_percent"] for r in rows),100.0)
                    self.assertNotIn("pais",rows[0]);self.assertEqual(rows[1]["pais"],["9p"])
                    self.assertEqual(len(client.calls),1);self.assertEqual(instance.billed,183)
                    self.assertEqual(instance.uncertain,0)
                    # A recommendation does not end the actual hand.
                    self.assertTrue(instance.hand_active)

    def test_matching_optional_actor_is_normalised_to_canonical_mjai(self):
        instance,_,_=adapter([answer({"type":"ryukyoku","actor":1},[])],score_mode="weights")
        out=instance.react(self.opening(3,1))
        self.assertEqual({k:v for k,v in out.items() if k!="meta"},{"type":"ryukyoku"})
        self.assertEqual(out["meta"]["show"]["items"][0]["value"],"100.0%")

    def test_explicit_wrong_or_malformed_actor_is_still_rejected(self):
        for actor in (0,None,True,"1",5):
            with self.subTest(actor=actor):
                instance,_,_=adapter([answer({"type":"ryukyoku","actor":actor})])
                out=instance.react(self.opening(3,1))
                self.assertEqual(out["type"],"none")
                self.assertIn("座位",out["meta"]["show"]["items"][0]["label"])

    def test_other_actions_still_require_matching_actor(self):
        for action in ({"type":"dahai","pai":"9p","tsumogiri":False},
                       {"type":"dahai","actor":0,"pai":"9p","tsumogiri":False},
                       {"type":"hora","target":1}):
            with self.subTest(action=action):
                instance,_,_=adapter([answer(action)])
                out=instance.react(self.opening(3,1))
                self.assertEqual(out["type"],"none")
                self.assertIn("座位",out["meta"]["show"]["items"][0]["label"])

class DecisionOptimizationTests(unittest.TestCase):
    def riichi_batch(self, players=4, tile="9s", choices=None):
        events=deepcopy(configure.sample_events(players))
        events += [{"type":"reach","actor":0},
                   {"type":"dahai","actor":0,"pai":"P","tsumogiri":False},
                   {"type":"reach_accepted","actor":0},
                   {"type":"tsumo","actor":1,"pai":"?"},
                   {"type":"dahai","actor":1,"pai":"C","tsumogiri":True},
                   {"type":"tsumo","actor":0,"pai":tile}]
        if choices is not None:
            events[-1]["_ap_legal_actions"]=choices
        return [{**START,"num_players":players}]+events

    def test_riichi_forced_draw_is_local_in_both_modes_and_no_usage_row(self):
        for players in (3,4):
            instance,client,_=adapter(score_mode="weights")
            out=instance.react(self.riichi_batch(players,choices=[{"type":"dahai","pai":"9s"}]))
            self.assertEqual((out["type"],out["pai"],out["tsumogiri"]),("dahai","9s",True))
            self.assertEqual(client.calls,[])
            self.assertEqual(out["meta"]["archer"]["skipped_requests"],1)
            self.assertEqual(out["meta"]["show"]["items"][0]["value"],"100.0%")
            self.assertNotIn("Token",json.dumps(out["meta"]["show"]))

    def test_riichi_preserves_win_ankan_north_and_unknown_choices(self):
        for option in ({"type":"hora","actor":0,"target":0}, {"type":"ankan","consumed":["9s"]*4},
                       {"type":"kita","actor":0}, {"type":"ryukyoku","actor":0},
                       {"type":"unknown"}, None):
            instance,client,_=adapter()
            choices=None if option is None else [{"type":"dahai","pai":"9s"},option]
            instance.react(self.riichi_batch(choices=choices))
            self.assertEqual(len(client.calls),1,option)
            self.assertNotIn("_ap_legal_actions",json.dumps(client.calls[0][2]))

    def test_unconfirmed_empty_or_mismatched_draw_legals_are_not_skipped(self):
        for choices in ([],[{"type":"dahai","pai":"P"}],{},False):
            instance,client,_=adapter()
            batch=self.riichi_batch(choices=choices)
            instance.react(batch)
            self.assertEqual(len(client.calls),1)
        instance,client,_=adapter()
        batch=[START]+deepcopy(EVENTS)
        batch[-1]["_ap_legal_actions"]=[{"type":"dahai","pai":"4s"}]
        instance.react(batch)
        self.assertEqual(len(client.calls),1,"non-riichi choices remain engine decisions")

    def test_no_claim_is_local_but_ron_still_queries(self):
        for choices,expected in (([],0),([{"type":"none"}],0),
                                 ([{"type":"none"},{"type":"hora","actor":0,"target":1}],1)):
            instance,client,_=adapter()
            batch=self.riichi_batch()[:-1]
            batch[-1]["_ap_legal_actions"]=choices
            instance.react(batch)
            self.assertEqual(len(client.calls),expected)
            self.assertEqual(instance.hand["P"],0,"history is applied even if no query")

    def test_history_after_skipped_draw_reaches_next_real_decision(self):
        instance,client,_=adapter()
        instance.react(self.riichi_batch(choices=[{"type":"dahai","pai":"9s"}]))
        instance.react([{"type":"dahai","actor":0,"pai":"9s","tsumogiri":True},
                        {"type":"tsumo","actor":1,"pai":"?"},
                        {"type":"dahai","actor":1,"pai":"C","tsumogiri":True},
                        {"type":"tsumo","actor":0,"pai":"9s",
                         "_ap_legal_actions":[{"type":"dahai","pai":"9s"},{"type":"hora","actor":0,"target":0}]}])
        self.assertEqual(len(client.calls),1)
        sent=client.calls[0][2]
        self.assertEqual(len([e for e in sent if e["type"]=="tsumo" and e["actor"]==0]),3)
        self.assertTrue(any(e.get("pai")=="9s" and e["type"]=="dahai" for e in sent))
        self.assertNotIn("_ap_legal_actions",json.dumps(sent))

    def test_new_hand_clears_riichi(self):
        instance,client,_=adapter()
        instance.react(self.riichi_batch(choices=[{"type":"dahai","pai":"9s"}]))
        instance.react(deepcopy(EVENTS))
        self.assertFalse(instance.riichi)
        self.assertEqual(len(client.calls),1)

    def test_sanma_score_scale_does_not_flatten_actual_sample(self):
        response=answer(candidates=[{"type":"dahai","pai":p,"q":q}
            for p,q in zip(["P","E","9p"],[-0.415,-1.036,-1.053])])
        instance,_,_=adapter([response],score_mode="weights")
        rows=instance.react([{**START,"num_players":3}]+configure.sample_events(3))["meta"]["show"]["items"]
        self.assertGreater(rows[0]["weight_percent"],48)
        self.assertEqual(sum(round(r["weight_percent"]*10) for r in rows),1000)

    def test_chi_candidates_show_complete_sequences_and_exact_red_tiles(self):
        events=deepcopy(EVENTS[:1])
        events[0]["tehais"][0]=["1m","2m","4m","5mr","5m","7p","8p","9p","2s","3s","E","E","P"]
        events += [{"type":"tsumo","actor":3,"pai":"?"},
                   {"type":"dahai","actor":3,"pai":"3m","tsumogiri":True}]
        action={"type":"chi","actor":0,"target":3,"pai":"3m","consumed":["4m","5mr"]}
        candidates=[{"type":"chi","kind":k,"q":3-i} for i,k in enumerate(["low","mid","high"])]
        instance,_,_=adapter([answer(action,candidates)],score_mode="weights")
        rows=instance.react([START]+events)["meta"]["show"]["items"]
        self.assertEqual([r["pais"] for r in rows],[["3m","4m","5mr"],["2m","3m","4m"],["1m","2m","3m"]])
        self.assertTrue(all(r["label"]=="吃" for r in rows))

    def test_connect_failure_can_retry_before_post_but_never_after_sending(self):
        with fixture_server(normal_responder) as (url,calls):
            client=ArcherClient({**SETTINGS,"api_url":url})
            real=client.new_connection
            class FailedConnect:
                def connect(self): raise ConnectionResetError()
                def close(self): pass
            attempts=[]
            def connect(timeout):
                attempts.append(timeout)
                return FailedConnect() if len(attempts)==1 else real(timeout)
            with patch.object(client,"new_connection",side_effect=connect):
                client.decide("fixture-4p",0,EVENTS)
            self.assertEqual(len(calls),1)
            self.assertEqual(client.last_timing["connect_attempts"],2)
            client.close()
        class FailedResponse:
            sock=None
            timeout=1
            sent=0
            def connect(self):pass
            def request(self,*a,**k):self.sent+=1
            def getresponse(self):raise ConnectionResetError()
            def close(self):pass
        connection=FailedResponse()
        client=ArcherClient(SETTINGS)
        with patch.object(client,"new_connection",return_value=connection) as maker:
            with self.assertRaises(ArcherError):client.decide("fixture-4p",0,EVENTS)
        self.assertEqual(connection.sent,1)
        self.assertEqual(maker.call_count,1)
        self.assertEqual(client.last_timing["failure_phase"],"response")

    def test_prepare_only_connects_and_never_sends_http(self):
        ready=threading.Event()
        class Connection:
            closed=False
            def connect(self):ready.set()
            def close(self):self.closed=True
        connection=Connection()
        client=ArcherClient(SETTINGS)
        with patch.object(client,"new_connection",return_value=connection):
            client.prepare_async()
            self.assertTrue(ready.wait(2))
            for _ in range(100):
                if client._warm_connection is not None:break
                time.sleep(0.005)
            self.assertTrue(client.take_prepared_connection())
            self.assertIs(client.connection,connection)
        client.close()
        self.assertTrue(connection.closed)


class ReadinessTests(unittest.TestCase):
    def test_readiness_uses_only_free_gets_and_hides_accounting_and_key(self):
        with fixture_server(normal_responder, persistent=True) as (url, calls):
            result=configure.readiness({**SETTINGS,"api_url":url})
            self.assertEqual(result["state"],"ready")
            self.assertEqual([m["players"] for m in result["models"]],[4,3])
            self.assertTrue(all(m["available"] for m in result["models"]))
            self.assertEqual([c["path"] for c in calls],["/v1/models","/v1/balance"])
            self.assertTrue(all(c["body"] is None for c in calls))
            self.assertNotIn(SETTINGS["api_key"],json.dumps(result))
            self.assertNotIn("balance",result)

    def test_readiness_checks_only_enabled_mode(self):
        with fixture_server(normal_responder) as (url, calls):
            result=configure.readiness({**SETTINGS,"api_url":url,"model":""},[3])
            self.assertEqual(result["state"],"ready")
            self.assertEqual([m["players"] for m in result["models"]],[3])

    def test_missing_model_fails_locally(self):
        with fixture_server(normal_responder) as (url, calls):
            result=configure.readiness({**SETTINGS,"api_url":url,"model_3p":""})
            self.assertEqual(result["state"],"error")
            self.assertIn("三麻",result["message"])
            self.assertEqual(calls,[])

    def test_zero_balance_and_unavailable_model_are_not_ready(self):
        def responder(path,body):
            if path=="/v1/balance":return 200,{"balance":0},{}
            return normal_responder(path,body)
        with fixture_server(responder) as (url,calls):
            result=configure.readiness({**SETTINGS,"api_url":url})
            self.assertEqual(result["message"],"账户余额不足")
            self.assertEqual(result["state"],"error")
        with fixture_server(normal_responder) as (url,calls):
            result=configure.readiness({**SETTINGS,"api_url":url,"model_3p":"not-open"})
            self.assertEqual(result["state"],"error")
            self.assertFalse(next(m for m in result["models"] if m["players"]==3)["available"])

    def test_error_payload_is_sanitized(self):
        def responder(path,body):
            return 401,{"error":{"code":"invalid_key","message":SETTINGS["api_key"]}},{}
        with fixture_server(responder) as (url,calls):
            result=configure.readiness({**SETTINGS,"api_url":url})
            self.assertEqual(result["state"],"error")
            self.assertIn("密钥",result["message"])
            self.assertNotIn(SETTINGS["api_key"],json.dumps(result))

    def test_readiness_cli_is_readonly_and_mode_specific(self):
        import shutil
        with fixture_server(normal_responder) as (url,calls), tempfile.TemporaryDirectory() as folder:
            target=Path(folder)
            for name in ("configure.py","archer_client.py","manifest.toml"):
                shutil.copy2(BOT_DIR/name,target/name)
            values={**SETTINGS,"api_url":url,"model":""}
            (target/"settings.toml").write_text(
                "\n".join(k+" = "+json.dumps(v) for k,v in values.items())+"\n",encoding="utf8")
            result=subprocess.run([sys.executable,str(target/"configure.py"),"--readiness","--modes","3"],
                                  cwd=target,capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
            status=json.loads(result.stdout)
            self.assertEqual(status["state"],"ready")
            self.assertEqual([m["players"] for m in status["models"]],[3])
            self.assertEqual([c["path"] for c in calls],["/v1/models","/v1/balance"])
            self.assertFalse((target/".akagi").exists(),"idle probes must not create private state files")
            self.assertNotIn(SETTINGS["api_key"],result.stdout+result.stderr)

    def test_no_key_fails_without_query(self):
        with fixture_server(normal_responder) as (url,calls):
            result=configure.readiness({**SETTINGS,"api_url":url,"api_key":""})
            self.assertEqual(result["state"],"error")
            self.assertEqual(calls,[])

if __name__ == "__main__":
    unittest.main(verbosity=2)
