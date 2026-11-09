//! Zhangxin decoded-message adapter. No game writes or frame injection.
//! The 92217 client shares the ordinary-riichi action/tile vocabulary with
//! Riichi City; framing, rule gates, sequence handling and metadata stay here.
use super::{Bridge, Direction, ParseResult, RiichiCityBridge};
use crate::schema::MjaiEvent;
use serde_json::Value;

pub struct ZhangxinBridge {
    core: RiichiCityBridge,
    instance: String,
    uid: i64,
    seq: u64,
    room: Option<Value>,
    active: bool,
    initial_draw: Option<i64>,
    pub issue: Option<String>,
}
impl Default for ZhangxinBridge {
    fn default() -> Self {
        Self::new()
    }
}
impl ZhangxinBridge {
    pub fn new() -> Self {
        Self {
            core: RiichiCityBridge::new(None, None),
            instance: String::new(),
            uid: 0,
            seq: 0,
            room: None,
            active: false,
            initial_draw: None,
            issue: None,
        }
    }
    pub fn reset(&mut self, why: &str) -> Vec<MjaiEvent> {
        let end = self.active;
        self.core = RiichiCityBridge::new(None, None);
        self.active = false;
        self.initial_draw = None;
        self.issue = Some(why.into());
        if end {
            vec![MjaiEvent::terminated_game()]
        } else {
            vec![]
        }
    }
    pub fn accept(&mut self, v: &Value) -> Vec<MjaiEvent> {
        if v["schema"].as_u64() != Some(1) {
            return self.reset("掌心消息格式未适配，等待重新入房。");
        }
        let Some(instance) = v["instance"]
            .as_str()
            .filter(|s| !s.is_empty() && s.len() <= 64)
        else {
            return self.reset("掌心客户端消息标识缺失，请更新插件。");
        };
        let mut restarted = vec![];
        if self.instance != instance {
            restarted = self.reset("掌心客户端已重新连接，等待新对局。");
            self.instance = instance.to_owned();
            self.seq = 0;
            self.uid = 0;
            self.room = None;
        }
        let uid = number(&v["uid"]).unwrap_or(0);
        let Some(seq) = v["seq"].as_u64() else {
            return vec![];
        };
        if uid <= 0 || seq == 0 {
            return vec![];
        }
        if seq <= self.seq {
            return vec![];
        }
        let mut out = restarted;
        if (self.seq != 0 && seq != self.seq + 1) || (self.uid != 0 && uid != self.uid) {
            out = self.reset("掌心消息中断，请重新进入下一场对局。");
            self.room = None;
        }
        self.seq = seq;
        self.uid = uid;
        let p = &v["packet"];
        let Some(cmd) = p["cmd"].as_str() else {
            return out;
        };
        let d = &p["data"];
        if cmd == "cmd_enter_room" {
            out.extend(self.reset("等待普通立直麻将开局。"));
            self.room = None;
            let Some(players) = d["players"].as_array() else {
                return out;
            };
            let n = number(&d["options"]["player_count"]).unwrap_or(0);
            let ids: Vec<_> = players
                .iter()
                .filter_map(|x| number(&x["user"]["user_id"]))
                .collect();
            let mode = number(&d["game_mode"]).or_else(|| number(&d["options"]["game_mode"]));
            if !matches!(n, 3 | 4)
                || ids.len() != n as usize
                || !ids.contains(&uid)
                || ids
                    .iter()
                    .any(|id| ids.iter().filter(|x| *x == id).count() != 1)
                || mode != Some(0)
            {
                self.issue = Some("此掌心房间或玩法暂不支持 AI。".into());
                return out;
            }
            // Wire roster order is not the seat order. The client explicitly
            // uses position_at (zero based) when resolving dealer_pos.
            let mut room = p.clone();
            let sorted = room["data"]["players"].as_array_mut().unwrap();
            if !(0..n).all(|seat| {
                sorted
                    .iter()
                    .filter(|p| number(&p["position_at"]) == Some(seat))
                    .count()
                    == 1
            }) {
                self.issue = Some("掌心座次资料不完整，已暂停 AI。".into());
                return out;
            }
            sorted.sort_by_key(|p| number(&p["position_at"]).unwrap());
            if !d["hand_status"].is_null() {
                self.issue = Some("中途进入的对局暂不分析，请在下一场开局前连接。".into());
                return out;
            }
            self.room = Some(room);
            self.issue = Some("等待开局。".into());
            return out;
        }
        let mut own_opening_without_draw = false;
        if cmd == "cmd_game_start" {
            if self.room.is_none() {
                self.issue = Some("请重新进入房间以同步玩家座次。".into());
                return out;
            }
            // Live 92217 traces omit game_mode at game_start. Inherit only
            // the explicitly validated room mode; never assume missing means 0.
            let room_data = &self.room.as_ref().unwrap()["data"];
            let mode = number(&d["game_mode"])
                .or_else(|| number(&room_data["game_mode"]))
                .or_else(|| number(&room_data["options"]["game_mode"]));
            if mode != Some(0) || d["si_dou_game"].as_bool() == Some(true) {
                out.extend(self.reset("特殊玩法暂不支持 AI。"));
                return out;
            }
            let n = number(&self.room.as_ref().unwrap()["data"]["options"]["player_count"]).unwrap()
                as usize;
            let Some(hand) = d["hand_cards"].as_array() else {
                out.extend(self.reset("开局手牌缺失，已暂停 AI。"));
                return out;
            };
            let dealer = number(&d["dealer_pos"]);
            let users = d["user_info_list"].as_array();
            let room_ids: Vec<_> = self.room.as_ref().unwrap()["data"]["players"]
                .as_array()
                .unwrap()
                .iter()
                .filter_map(|p| number(&p["user"]["user_id"]))
                .collect();
            if !matches!(hand.len(), 13 | 14)
                || hand.iter().any(|c| !valid_card(c))
                || !valid_card(&d["bao_pai_card"])
                || !matches!(number(&d["quan_feng"]), Some(49 | 65 | 81 | 97))
                || !dealer.is_some_and(|x| x >= 0 && x < n as i64)
                || !users.is_some_and(|us| {
                    us.len() == n
                        && room_ids.iter().all(|id| {
                            us.iter()
                                .filter(|u| {
                                    number(&u["user_id"]) == Some(*id)
                                        && number(&u["hand_points"]).is_some()
                                })
                                .count()
                                == 1
                        })
                })
            {
                out.extend(self.reset("开局数据未通过校验，已暂停 AI。"));
                return out;
            }
            if !self.active {
                self.core = RiichiCityBridge::new(None, None);
                self.core.decoded_events(uid, self.room.as_ref().unwrap());
            }
            let dealer_uid = room_ids[dealer.unwrap() as usize];
            if hand.len() == 14 && dealer_uid != uid {
                out.extend(self.reset("起手牌与庄家资料不一致，已暂停 AI。"));
                return out;
            }
            own_opening_without_draw = hand.len() == 13 && dealer_uid == uid;
            self.active = true;
            self.issue = None;
            self.initial_draw = if hand.len() == 14 {
                number(&hand[13])
            } else {
                None
            };
        } else if !self.active {
            return out;
        }
        if cmd == "cmd_send_current_action" {
            if let Some(first) = self.initial_draw.take() {
                if number(&d["in_card"]) == Some(first) {
                    return out;
                }
            }
        }
        if cmd == "cmd_game_action_brc" {
            self.initial_draw = None;
        }
        if cmd == "cmd_game_action_brc" {
            let valid = d["action_info"].as_array().is_some_and(|actions| {
                actions.iter().all(|a| {
                    number(&a["action"]).is_some_and(|n| (0..=14).contains(&n))
                        && self.room.as_ref().unwrap()["data"]["players"]
                            .as_array()
                            .unwrap()
                            .iter()
                            .any(|p| number(&p["user"]["user_id"]) == number(&a["user_id"]))
                })
            });
            if !valid {
                out.extend(self.reset("掌心动作数据未适配，已暂停 AI。"));
                return out;
            }
        }
        let mut events = self.core.decoded_events(uid, p);
        if own_opening_without_draw {
            events.retain(|e| !matches!(e,MjaiEvent::Tsumo{pai,..} if pai=="?"));
        }
        // Never tag Zhangxin games as Riichi City in history.
        for e in &mut events {
            if let MjaiEvent::StartGame { game_meta, .. } = e {
                *game_meta = None;
            }
        }
        if cmd == "cmd_room_end" {
            self.active = false;
            self.room = None;
        }
        out.extend(events);
        out
    }
}
fn number(v: &Value) -> Option<i64> {
    v.as_i64().or_else(|| v.as_str()?.parse().ok())
}
fn valid_card(v: &Value) -> bool {
    number(v).is_some_and(|c| {
        c > 0 && crate::bridge::riichi_city::consts::card_to_mjai_str(c as u32) != "?"
    })
}
impl Bridge for ZhangxinBridge {
    fn parse(&mut self, direction: Direction, bytes: &[u8]) -> ParseResult {
        if direction != Direction::Down {
            return ParseResult::empty();
        }
        let Ok(v) = serde_json::from_slice(bytes) else {
            return ParseResult::empty();
        };
        ParseResult::just_events(self.accept(&v))
    }
    fn build(&mut self, _: &MjaiEvent) -> Option<Vec<u8>> {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    fn feed(b: &mut ZhangxinBridge, seq: u64, cmd: &str, data: Value) -> Vec<MjaiEvent> {
        b.accept(&json!({"schema":1,"instance":"test","uid":"11","seq":seq,"packet":{"cmd":cmd,"room_id":"r","data":data}}))
    }
    fn room(n: usize) -> Value {
        let mut players: Vec<_> = (0..n)
            .map(|i| json!({"position_at":i,"user":{"user_id":11+i,"nickname":format!("p{i}")}}))
            .collect();
        players.reverse();
        json!({"game_mode":0,"options":{"player_count":n},"players":players})
    }
    fn opening(n: usize, dealer: usize) -> Value {
        let mut hand = vec![1, 2, 3, 4, 5, 6, 7, 8, 9, 17, 18, 19, 33];
        if dealer == 0 {
            hand.push(34)
        }
        json!({"game_mode":0,"dealer_pos":dealer,"quan_feng":49,"bao_pai_card":5,"hand_cards":hand,"user_info_list":(0..n).map(|i|json!({"user_id":11+i,"hand_points":25000})).collect::<Vec<_>>()})
    }
    #[test]
    fn ordinary_start_has_correct_seat_scores_and_red_tile() {
        let mut b = ZhangxinBridge::new();
        feed(&mut b, 1, "cmd_enter_room", room(4));
        let e = feed(&mut b, 2, "cmd_game_start", opening(4, 1));
        assert!(matches!(
            &e[0],
            MjaiEvent::StartGame {
                id: Some(3),
                num_players: 4,
                game_meta: None,
                ..
            }
        ));
        assert!(
            matches!(&e[1],MjaiEvent::StartKyoku{scores,num_players:4,..} if scores==&vec![25000;4])
        );
        let e = feed(&mut b, 3, "cmd_send_current_action", json!({"in_card":261}));
        assert!(matches!(&e[0],MjaiEvent::Tsumo{actor:3,pai} if pai=="5pr"));
    }
    #[test]
    fn dealer_first_prompt_is_not_a_second_draw() {
        let mut b = ZhangxinBridge::new();
        feed(&mut b, 1, "cmd_enter_room", room(3));
        let e = feed(&mut b, 2, "cmd_game_start", opening(3, 0));
        assert!(matches!(
            &e[0],
            MjaiEvent::StartGame {
                id: Some(0),
                num_players: 3,
                ..
            }
        ));
        assert_eq!(
            e.iter()
                .filter(|e| matches!(e, MjaiEvent::Tsumo { .. }))
                .count(),
            1
        );
        assert!(feed(&mut b, 3, "cmd_send_current_action", json!({"in_card":34})).is_empty());
        let e = feed(
            &mut b,
            4,
            "cmd_game_action_brc",
            json!({"action_info":[{"action":11,"user_id":11,"card":34,"move_cards_pos":[14,14]}]}),
        );
        assert!(matches!(
            &e[0],
            MjaiEvent::Dahai {
                actor: 0,
                tsumogiri: true,
                ..
            }
        ));
    }
    #[test]
    fn dealer_thirteen_tiles_waits_for_real_draw() {
        let mut b = ZhangxinBridge::new();
        feed(&mut b, 1, "cmd_enter_room", room(4));
        let mut d = opening(4, 0);
        d["hand_cards"].as_array_mut().unwrap().pop();
        let e = feed(&mut b, 2, "cmd_game_start", d);
        assert_eq!(
            e.iter()
                .filter(|e| matches!(e, MjaiEvent::Tsumo { .. }))
                .count(),
            0
        );
        assert_eq!(
            feed(&mut b, 3, "cmd_send_current_action", json!({"in_card":34})).len(),
            1
        );
    }
    #[test]
    fn unsupported_mode_reconnect_and_missing_seat_never_start_ai() {
        for case in 0..3 {
            let mut b = ZhangxinBridge::new();
            let mut r = room(4);
            if case == 0 {
                r["game_mode"] = json!(2)
            }
            if case == 1 {
                r["hand_status"] = json!({"dealer_pos":1})
            }
            if case == 2 {
                r["players"][0]["position_at"] = json!(99)
            }
            feed(&mut b, 1, "cmd_enter_room", r);
            assert!(feed(&mut b, 2, "cmd_game_start", opening(4, 0)).is_empty());
            assert!(b.issue.is_some());
        }
    }
    #[test]
    fn lost_or_duplicate_messages_cannot_continue_a_corrupt_hand() {
        let mut b = ZhangxinBridge::new();
        feed(&mut b, 1, "cmd_enter_room", room(4));
        feed(&mut b, 2, "cmd_game_start", opening(4, 0));
        assert!(feed(&mut b, 2, "cmd_game_start", opening(4, 0)).is_empty());
        let e = feed(&mut b, 4, "cmd_send_current_action", json!({"in_card":34}));
        assert!(matches!(&e[0], MjaiEvent::EndGame { .. }));
        assert!(feed(&mut b, 5, "cmd_game_start", opening(4, 0)).is_empty());
        feed(&mut b, 6, "cmd_enter_room", room(4));
        assert!(!feed(&mut b, 7, "cmd_game_start", opening(4, 0)).is_empty());
    }
    #[test]
    fn unknown_cards_and_missing_identity_fail_closed() {
        let mut b = ZhangxinBridge::new();
        feed(&mut b, 1, "cmd_enter_room", room(4));
        let mut d = opening(4, 0);
        d["hand_cards"][0] = json!(65535);
        assert!(feed(&mut b, 2, "cmd_game_start", d).is_empty());
        let mut r = room(4);
        r["players"][0]["user"]["user_id"] = json!(11);
        feed(&mut b, 3, "cmd_enter_room", r);
        assert!(feed(&mut b, 4, "cmd_game_start", opening(4, 0)).is_empty());
        assert!(b.build(&MjaiEvent::end_game()).is_none());
    }
}

#[cfg(test)]
mod restart_test {
    use super::*;
    use serde_json::json;
    #[test]
    fn restarting_client_resets_sequence_namespace() {
        let mut b = ZhangxinBridge::new();
        let frame = |instance: &str, seq| json!({"schema":1,"instance":instance,"seq":seq,"uid":11,"packet":{"cmd":"ignored","data":{}}});
        b.accept(&frame("first", 12));
        b.accept(&frame("second", 1));
        assert_eq!(b.seq, 1);
        assert_eq!(b.instance, "second");
    }
}

#[cfg(test)]
mod live_shape_regression {
    use super::*;
    use serde_json::json;
    #[test]
    fn start_without_mode_inherits_only_explicit_room_mode() {
        let envelope = |seq, cmd, data| json!({"schema":1,"instance":"test","uid":11,"seq":seq,"packet":{"cmd":cmd,"data":data}});
        let r = json!({"game_mode":0,"options":{"player_count":3},"players":(0..3).map(|i|json!({"position_at":i,"user":{"user_id":11+i}})).collect::<Vec<_>>()});
        // Matches the captured client shape: mode exists on room, not start.
        let d = json!({"dealer_pos":1,"quan_feng":49,"bao_pai_card":5,"hand_cards":[1,2,3,4,5,6,7,8,9,17,18,19,33],"user_info_list":(0..3).map(|i|json!({"user_id":11+i,"hand_points":30000})).collect::<Vec<_>>()});
        let mut b = ZhangxinBridge::new();
        b.accept(&envelope(1, "cmd_enter_room", r.clone()));
        assert!(b
            .accept(&envelope(2, "cmd_game_start", d.clone()))
            .iter()
            .any(|e| matches!(e, MjaiEvent::StartKyoku { .. })));
        let mut special = d.clone();
        special["game_mode"] = json!(2);
        assert!(!b
            .accept(&envelope(3, "cmd_game_start", special))
            .iter()
            .any(|e| matches!(e, MjaiEvent::StartKyoku { .. })));
        let mut unknown = r;
        unknown.as_object_mut().unwrap().remove("game_mode");
        let mut b = ZhangxinBridge::new();
        b.accept(&envelope(1, "cmd_enter_room", unknown));
        assert!(b.accept(&envelope(2, "cmd_game_start", d)).is_empty());
    }
    // Optional private replay. No fixtures, user IDs or hand data enter git.
    #[test]
    #[ignore = "requires a local private trace via AKAGIPLUS_ZHANGXIN_TRACE"]
    fn replay_private_trace_through_game_tracker() {
        let path = std::env::var("AKAGIPLUS_ZHANGXIN_TRACE").expect("private trace path");
        let raw = std::fs::read_to_string(path).unwrap();
        let mut bridge = ZhangxinBridge::new();
        let mut tracker = crate::game_state::GameTracker::new();
        let (mut frames, mut events, mut starts, mut decisions) = (0, 0, 0, 0);
        for line in raw.lines().filter(|s| !s.is_empty()) {
            let value: Value = serde_json::from_str(line).unwrap();
            frames += 1;
            for event in bridge.accept(&value) {
                starts += usize::from(matches!(event, MjaiEvent::StartGame { .. }));
                tracker.handle(&event).expect("valid game tracker event");
                decisions += usize::from(tracker.our_seat_can_act() == Some(true));
                events += 1;
            }
        }
        assert!(
            starts > 0 && events > 20 && decisions > 0,
            "trace must reach AI decisions"
        );
        assert!(bridge.issue.is_none(), "trace ended in a blocked state");
        println!("private replay: frames={frames}, mjai_events={events}, games={starts}, decision_windows={decisions}");
    }
}
