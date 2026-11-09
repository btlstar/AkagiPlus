//! Read-only, normalized Amatsuki events from the native capture worker.
use super::{Bridge, Direction, ParseResult};
use crate::schema::{GameEndReason, MjaiEvent};
use serde_json::Value;

#[derive(Default)]
pub struct AmatsukiBridge {
    active: bool,
}
impl AmatsukiBridge {
    pub fn accept(&mut self, value: &Value) -> anyhow::Result<Vec<MjaiEvent>> {
        let mut event: MjaiEvent = serde_json::from_value(value["event"].clone())?;
        if let MjaiEvent::StartGame {
            num_players, id, ..
        } = &event
        {
            anyhow::ensure!(
                matches!(num_players, 3 | 4) && id.is_some_and(|id| id < *num_players),
                "无效的天月座次"
            );
            self.active = true;
        } else if !self.active {
            return Ok(vec![]);
        }
        if let MjaiEvent::EndGame {
            reason,
            final_scores,
            ..
        } = &mut event
        {
            if value["terminated"].as_bool() == Some(true) {
                *reason = GameEndReason::Terminated;
            }
            *final_scores = value
                .get("final_scores")
                .and_then(|v| serde_json::from_value(v.clone()).ok());
            self.active = false;
        }
        Ok(vec![event])
    }
}
impl Bridge for AmatsukiBridge {
    fn parse(&mut self, direction: Direction, content: &[u8]) -> ParseResult {
        if direction != Direction::Down {
            return ParseResult::empty();
        }
        let events = serde_json::from_slice(content)
            .ok()
            .and_then(|value| self.accept(&value).ok())
            .unwrap_or_default();
        ParseResult::just_events(events)
    }
    fn build(&mut self, _: &MjaiEvent) -> Option<Vec<u8>> {
        None
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn requires_start_and_preserves_final_result() {
        let mut b = AmatsukiBridge::default();
        assert!(b
            .accept(&json!({"event":{"type":"tsumo","actor":0,"pai":"1m"}}))
            .unwrap()
            .is_empty());
        b.accept(&json!({"event":{"type":"start_game","names":["A","B","C","D"],"id":2,"num_players":4}})).unwrap();
        let end = b
            .accept(&json!({"event":{"type":"end_game"},"final_scores":[30000,20000,25000,25000]}))
            .unwrap();
        assert!(
            matches!(&end[0],MjaiEvent::EndGame{reason:GameEndReason::Confirmed,final_scores:Some(scores),..} if scores[0]==30000)
        );
        assert!(b.build(&MjaiEvent::None).is_none());
    }
}
