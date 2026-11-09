# MajsoulMax adapter provenance

- Upstream logic: [Avenshy/MajsoulMax v2026.07.07](https://github.com/Avenshy/MajsoulMax/tree/v2026.07.07), GPL-3.0.
- Imported through the locally developed MahjongCopilotPlus `majsoulmax` module on 2026-11-05; source hashes are recorded in `SOURCE.json`.
- Data/protocol snapshot: [Avenshy/MajsoulData 0.16.289-4.0.51](https://github.com/Avenshy/MajsoulData/releases/tag/0.16.289-4.0.51), 125 characters / 516 skins. Exact hashes are retained in `majsoulmax/config/data_version.json`.
- Existing CopilotPlus changes retained: dynamic descriptor loading, resource validation, preservation of unknown fields, and friend-room character/avatar/skin alignment.
- AkagiPlus adaptations dated 2026-11-05: standalone JSONL worker, minimal RPC correlation, logging independent of Copilot, atomic private settings writes, opt-in execution, and separation of read-only snapshot from writable choices.
- No private settings, browser profile, account credentials, certificate or third-party executable was imported.

The MajsoulMax implementation and its adapted files retain GPL-3.0, see `LICENSE.txt`. Akagi's Apache-2.0 license and original NOTICE remain at repository root and under `LICENSES`. The original Rust/TypeScript glue files carry Apache-2.0. Game names, characters, images, sound and other third-party assets retain their respective owners' rights. This file does not grant additional rights to those assets.
