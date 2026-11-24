use crate::proto::lq::ViewSlot;
use anyhow::{Context, Result, bail, ensure};
use prost::Message;
use prost_reflect::{DescriptorPool, prost_types::FileDescriptorSet};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    collections::{HashMap, HashSet},
    path::{Path, PathBuf},
};
use tracing::{error, info};

#[derive(Serialize, Deserialize, Debug, Default, Clone)]
#[serde(default, deny_unknown_fields)]
pub struct MaxData {
    pub character: Vec<u32>,
    pub skin: Vec<u32>,
    pub title: Vec<u32>,
    pub item: Vec<u32>,
    pub loading_image: Vec<u32>,
    pub emoji: HashMap<u32, Vec<u32>>,
    pub endings: Vec<u32>,
}

impl MaxData {
    pub fn load(dir: &Path) -> Result<Self> {
        let content =
            std::fs::read_to_string(dir.join("max_data.yaml")).context("无法读取max_data.yaml")?;
        let mut data = parse_max_data(&content)?;
        let local_path = dir.join("max_data.local.json");
        let local_content = match std::fs::read_to_string(&local_path) {
            Ok(content) => content,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(data),
            Err(error) => return Err(error).context("无法读取max_data.local.json"),
        };
        let local: MaxData =
            serde_json::from_str(&local_content).context("无法解析max_data.local.json")?;
        for ids in [
            &local.character,
            &local.skin,
            &local.title,
            &local.item,
            &local.loading_image,
            &local.endings,
        ] {
            ensure!(!ids.contains(&0), "本地资源清单包含无效的 ID 0");
        }
        ensure!(
            local
                .emoji
                .iter()
                .all(|(id, emojis)| *id != 0 && !emojis.is_empty() && !emojis.contains(&0)),
            "本地资源清单包含无效的表情数据"
        );
        let local_characters = local.character.clone();
        data.merge(local);
        for id in local_characters {
            let default_skin = ModSettings::default_avatar_id(id)?;
            ensure!(
                data.skin.contains(&default_skin),
                "本地角色 {id} 缺少默认皮肤 {default_skin}"
            );
        }
        info!(
            "已合并本地资源清单: {} 个角色, {} 个皮肤",
            data.character.len(),
            data.skin.len()
        );
        Ok(data)
    }

    fn merge(&mut self, local: Self) {
        fn append_unique(target: &mut Vec<u32>, extra: Vec<u32>) {
            let mut seen: HashSet<u32> = target.iter().copied().collect();
            target.extend(extra.into_iter().filter(|id| seen.insert(*id)));
        }
        append_unique(&mut self.character, local.character);
        append_unique(&mut self.skin, local.skin);
        append_unique(&mut self.title, local.title);
        append_unique(&mut self.item, local.item);
        append_unique(&mut self.loading_image, local.loading_image);
        append_unique(&mut self.endings, local.endings);
        for (id, emojis) in local.emoji {
            append_unique(self.emoji.entry(id).or_default(), emojis);
        }
    }
}

fn parse_max_data(content: &str) -> Result<MaxData> {
    let mut result = MaxData::default();
    let mut section = String::new();
    let mut emoji_character = None;

    for (line_number, raw_line) in content.lines().enumerate() {
        let line = raw_line.trim_end_matches('\r');
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        if !line.starts_with(' ') && !trimmed.starts_with("- ") {
            ensure!(
                trimmed.ends_with(':'),
                "invalid max_data.yaml line {}",
                line_number + 1
            );
            section = trimmed.trim_end_matches(':').to_string();
            emoji_character = None;
            ensure!(
                matches!(
                    section.as_str(),
                    "character" | "skin" | "title" | "item" | "loading_image" | "emoji" | "endings"
                ),
                "unknown max_data.yaml section on line {}",
                line_number + 1
            );
            continue;
        }

        if section == "emoji" && line.starts_with("  ") && trimmed.ends_with(':') {
            let id = trimmed
                .trim_end_matches(':')
                .parse::<u32>()
                .with_context(|| format!("invalid emoji character on line {}", line_number + 1))?;
            result.emoji.entry(id).or_default();
            emoji_character = Some(id);
            continue;
        }

        ensure!(
            trimmed.starts_with("- "),
            "invalid max_data.yaml line {}",
            line_number + 1
        );
        let id = trimmed[2..]
            .parse::<u32>()
            .with_context(|| format!("invalid data ID on line {}", line_number + 1))?;
        match section.as_str() {
            "character" => result.character.push(id),
            "skin" => result.skin.push(id),
            "title" => result.title.push(id),
            "item" => result.item.push(id),
            "loading_image" => result.loading_image.push(id),
            "endings" => result.endings.push(id),
            "emoji" => result
                .emoji
                .get_mut(&emoji_character.context("emoji item without character")?)
                .expect("emoji character was inserted above")
                .push(id),
            _ => bail!(
                "list item outside a max_data.yaml section on line {}",
                line_number + 1
            ),
        }
    }

    ensure!(
        !result.character.is_empty(),
        "max_data.yaml has no characters"
    );
    ensure!(!result.skin.is_empty(), "max_data.yaml has no skins");
    ensure!(!result.title.is_empty(), "max_data.yaml has no titles");
    ensure!(!result.item.is_empty(), "max_data.yaml has no items");
    ensure!(
        !result.loading_image.is_empty(),
        "max_data.yaml has no loading images"
    );
    ensure!(!result.emoji.is_empty(), "max_data.yaml has no emoji data");
    ensure!(
        result.emoji.values().all(|items| !items.is_empty()),
        "max_data.yaml has an empty emoji list"
    );
    ensure!(!result.endings.is_empty(), "max_data.yaml has no endings");
    Ok(result)
}

#[derive(Serialize, Deserialize, Debug, Default, Clone)]
#[serde(rename_all = "camelCase")]
pub struct Settings {
    pub send_method: Vec<String>,
    pub send_action: Vec<String>,
    pub proxy_addr: String,
    pub api_url: String,
    helper_switch: bool,
    mod_switch: bool,
    auto_update: bool,
    liqi_version: String,
    github_token: String,
    #[serde(default)]
    req_proxy: Option<url::Url>,
    #[serde(skip)]
    methods_set: HashSet<String>,
    #[serde(skip)]
    actions_set: HashSet<String>,
    #[serde(skip)]
    pub desc: DescriptorPool,
    #[serde(skip)]
    pub proto_json: Value,
    #[serde(skip)]
    dir: PathBuf,
}

const APP_USER_AGENT: &str = concat!(env!("CARGO_PKG_NAME"), "/", env!("CARGO_PKG_VERSION"));

fn resolve_config_dir(arg_dir: &Path, exe: &Path) -> Result<PathBuf> {
    let exe_dir = exe.parent().context("无法获取可执行文件的父目录")?;
    let mut candidates = vec![arg_dir.to_path_buf(), exe_dir.join("liqi_config")];
    // cargo build puts the executable under target/[<triple>/]release or debug.
    // Keep using the project's single configuration instead of making a second copy.
    if let Some(target_dir) = exe_dir
        .ancestors()
        .take(3)
        .find(|dir| dir.file_name().is_some_and(|name| name == "target"))
        && let Some(project_dir) = target_dir.parent()
    {
        candidates.push(project_dir.join("liqi_config"));
    }
    for candidate in &candidates {
        if candidate.join("settings.json").is_file() {
            return candidate
                .canonicalize()
                .with_context(|| format!("无法访问配置目录: {}", candidate.display()));
        }
    }
    bail!(
        "找不到 liqi_config/settings.json。请将完整的 liqi_config 文件夹与程序放在同一目录。已检查: {}",
        candidates
            .iter()
            .map(|path| path.display().to_string())
            .collect::<Vec<_>>()
            .join("; ")
    )
}

impl Settings {
    fn create_github_client(&self) -> Result<reqwest::Client> {
        let mut builder = reqwest::Client::builder().user_agent(APP_USER_AGENT);
        if let Some(proxy) = &self.req_proxy {
            builder = builder.proxy(reqwest::Proxy::all(proxy.clone())?);
        }
        builder.build().context("Failed to build HTTP client")
    }

    pub fn new(arg_dir: &Path) -> Result<Self> {
        let exe = std::env::current_exe().context("无法获取当前可执行文件路径")?;
        let dir = resolve_config_dir(arg_dir, &exe)?;
        let content =
            std::fs::read_to_string(dir.join("settings.json")).context("无法读取settings.json")?;
        let mut settings: Settings =
            serde_json::from_str(&content).context("无法解析settings.json")?;
        settings.methods_set = settings.send_method.iter().cloned().collect();
        settings.actions_set = settings.send_action.iter().cloned().collect();

        let descriptor_bytes = std::fs::read(dir.join("liqi.desc")).context("无法读取liqi.desc")?;
        let descriptor_set =
            FileDescriptorSet::decode(descriptor_bytes.as_slice()).context("无法解析liqi.desc")?;
        settings.desc = DescriptorPool::from_file_descriptor_set(descriptor_set)
            .context("无法构建liqi descriptor pool")?;
        settings.proto_json = serde_json::from_str(
            &std::fs::read_to_string(dir.join("liqi.json")).context("无法读取liqi.json")?,
        )
        .context("无法解析liqi.json")?;
        settings.dir = dir;
        Ok(settings)
    }

    pub fn data_dir(&self) -> &Path {
        &self.dir
    }
    pub fn is_method(&self, method: &str) -> bool {
        self.methods_set.contains(method)
    }
    pub fn is_action(&self, action: &str) -> bool {
        self.actions_set.contains(action)
    }
    pub fn helper_on(&self) -> bool {
        self.helper_switch
    }
    pub fn mod_on(&self) -> bool {
        self.mod_switch
    }
    pub fn auto_update(&self) -> bool {
        self.auto_update
    }

    pub async fn update(&mut self) -> Result<bool> {
        let client = self.create_github_client()?;
        let mut request = client
            .get("https://api.github.com/repos/Avenshy/MajsoulData/releases/latest")
            .header("X-GitHub-Api-Version", "2022-11-28")
            .timeout(std::time::Duration::from_secs(10));
        if !self.github_token.is_empty() {
            request = request.header("Authorization", format!("Bearer {}", self.github_token));
        }
        let response = request
            .send()
            .await
            .context("Failed to get MajsoulData latest release")?
            .error_for_status()
            .context("MajsoulData latest release request failed")?;
        if response
            .headers()
            .get("X-RateLimit-Remaining")
            .and_then(|value| value.to_str().ok())
            == Some("0")
        {
            bail!("GitHub API rate limit exceeded");
        }
        let release: Value = response.json().await?;
        let version = release["tag_name"]
            .as_str()
            .context("MajsoulData release has no tag_name")?;
        if self.liqi_version == version {
            info!("无需更新协议和资源数据, 当前版本: {version}");
            return Ok(false);
        }

        let assets = release["assets"]
            .as_array()
            .context("MajsoulData release has no assets")?;
        let mut descriptor = None;
        let mut max_data = None;
        for asset in assets {
            match asset["name"].as_str().unwrap_or_default() {
                "liqi.desc" => descriptor = Some(self.download_asset(asset).await?),
                "max_data.yaml" => max_data = Some(self.download_asset(asset).await?),
                _ => {}
            }
        }
        let descriptor = descriptor.context("MajsoulData release lacks liqi.desc")?;
        let max_data = max_data.context("MajsoulData release lacks max_data.yaml")?;
        let rpc_map = generate_liqi_json(&descriptor)?;
        parse_max_data(
            std::str::from_utf8(&max_data).context("max_data.yaml is not valid UTF-8")?,
        )?;

        // Write all related files only after every required asset has downloaded successfully.
        std::fs::write(self.dir.join("liqi.desc"), descriptor)?;
        std::fs::write(self.dir.join("max_data.yaml"), max_data)?;
        std::fs::write(self.dir.join("liqi.json"), rpc_map)?;
        self.liqi_version = version.to_string();
        std::fs::write(
            self.dir.join("settings.json"),
            serde_json::to_string_pretty(self)?,
        )?;
        info!("协议和资源数据更新完成: {version}");
        Ok(true)
    }

    async fn download_asset(&self, asset: &Value) -> Result<Vec<u8>> {
        let name = asset["name"].as_str().context("No asset name")?;
        ensure!(
            matches!(name, "liqi.desc" | "max_data.yaml"),
            "Unsupported asset: {name}"
        );
        let url = asset["browser_download_url"]
            .as_str()
            .context("No asset URL")?;
        let client = self.create_github_client()?;
        let mut request = client
            .get(url)
            .header("X-GitHub-Api-Version", "2022-11-28")
            .timeout(std::time::Duration::from_secs(10));
        if !self.github_token.is_empty() {
            request = request.header("Authorization", format!("Bearer {}", self.github_token));
        }
        let response = request
            .send()
            .await
            .context("Failed to download asset")?
            .error_for_status()
            .context("Asset download failed")?;
        Ok(response.bytes().await?.to_vec())
    }
}

fn generate_liqi_json(bytes: &[u8]) -> Result<String> {
    let descriptors = FileDescriptorSet::decode(bytes).context("无法解析liqi.desc")?;
    let mut rpc_map = serde_json::Map::new();
    for file in descriptors.file {
        let package = file.package.unwrap_or_default();
        for service in file.service {
            let service_name = service.name.context("service without name in liqi.desc")?;
            for method in service.method {
                let method_name = method.name.context("method without name in liqi.desc")?;
                let input_type = method
                    .input_type
                    .context("method without input type in liqi.desc")?;
                let output_type = method
                    .output_type
                    .context("method without output type in liqi.desc")?;
                let full_method = format!(".{package}.{service_name}.{method_name}");
                rpc_map.insert(
                    full_method,
                    serde_json::json!({"req": input_type, "resp": output_type}),
                );
            }
        }
    }
    Ok(serde_json::to_string(&Value::Object(rpc_map))?)
}

#[cfg(test)]
mod tests {
    use super::*;

    struct ConfigFixture(PathBuf);

    impl ConfigFixture {
        fn new() -> Self {
            let unique = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos();
            let path = std::env::temp_dir().join(format!(
                "majsoul-config-test-{}-{unique}",
                std::process::id()
            ));
            std::fs::create_dir_all(&path).unwrap();
            Self(path)
        }

        fn config(&self, relative: &str) -> PathBuf {
            let dir = self.0.join(relative);
            std::fs::create_dir_all(&dir).unwrap();
            std::fs::write(dir.join("settings.json"), "{}").unwrap();
            dir.canonicalize().unwrap()
        }
    }

    impl Drop for ConfigFixture {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn double_click_finds_project_config_for_cargo_build_layouts() {
        let fixture = ConfigFixture::new();
        let config = fixture.config("liqi_config");
        for relative in [
            "target/release/majsoul_max_rs.exe",
            "target/debug/majsoul_max_rs.exe",
            "target/x86_64-pc-windows-msvc/release/majsoul_max_rs.exe",
        ] {
            let exe = fixture.0.join(relative);
            assert_eq!(
                resolve_config_dir(&fixture.0.join("missing"), &exe).unwrap(),
                config
            );
        }
    }

    #[test]
    fn portable_executable_skips_an_empty_working_directory_config() {
        let fixture = ConfigFixture::new();
        let config = fixture.config("portable/liqi_config");
        let empty = fixture.0.join("empty");
        std::fs::create_dir_all(&empty).unwrap();
        let exe = fixture.0.join("portable/majsoul_max_rs.exe");
        assert_eq!(resolve_config_dir(&empty, &exe).unwrap(), config);

        let explicit = fixture.config("custom");
        assert_eq!(resolve_config_dir(&explicit, &exe).unwrap(), explicit);
    }

    #[test]
    fn missing_configuration_reports_where_to_put_it() {
        let fixture = ConfigFixture::new();
        let exe = fixture.0.join("portable/majsoul_max_rs.exe");
        let message = resolve_config_dir(&fixture.0.join("missing"), &exe)
            .unwrap_err()
            .to_string();
        assert!(message.contains("liqi_config/settings.json"));
        assert!(message.contains("portable"));
    }

    #[test]
    fn local_resources_survive_base_replacement_and_are_deduplicated() {
        let fixture = ConfigFixture::new();
        let base = include_str!("../liqi_config/max_data.yaml");
        std::fs::write(fixture.0.join("max_data.yaml"), base).unwrap();
        let original = MaxData::load(&fixture.0).unwrap();
        assert!(!original.character.contains(&20000999));
        std::fs::write(
            fixture.0.join("max_data.local.json"),
            r#"{"character":[200001,20000999,20000999],
                "skin":[400101,40099901],"emoji":{"200001":[999,999]}}"#,
        )
        .unwrap();
        for _ in 0..2 {
            // An upstream update replaces only the base file.
            std::fs::write(fixture.0.join("max_data.yaml"), base).unwrap();
            let data = MaxData::load(&fixture.0).unwrap();
            assert_eq!(
                data.character.iter().filter(|id| **id == 20000999).count(),
                1
            );
            assert_eq!(data.character.len(), original.character.len() + 1);
            assert!(data.skin.contains(&40099901));
            assert_eq!(
                data.emoji[&200001].iter().filter(|id| **id == 999).count(),
                1
            );
        }
    }

    #[test]
    fn invalid_local_resources_report_errors_without_changing_base() {
        let fixture = ConfigFixture::new();
        let base = include_str!("../liqi_config/max_data.yaml");
        std::fs::write(fixture.0.join("max_data.yaml"), base).unwrap();
        for content in [
            r#"{"character":[20000999]}"#,
            r#"{"character":[0]}"#,
            r#"{"skins":[40099901]}"#,
            r#"{"emoji":{"200001":[]}}"#,
            "{",
        ] {
            std::fs::write(fixture.0.join("max_data.local.json"), content).unwrap();
            assert!(MaxData::load(&fixture.0).is_err(), "{content}");
            assert_eq!(
                std::fs::read_to_string(fixture.0.join("max_data.yaml")).unwrap(),
                base
            );
        }
    }

    #[test]
    fn parses_bundled_max_data() {
        let data = parse_max_data(include_str!("../liqi_config/max_data.yaml")).unwrap();

        assert!(!data.character.is_empty());
        assert!(!data.skin.is_empty());
        assert!(!data.title.is_empty());
        assert!(!data.item.is_empty());
        assert!(!data.loading_image.is_empty());
        assert!(!data.endings.is_empty());
        assert!(data.emoji.values().all(|items| !items.is_empty()));
    }

    #[test]
    fn rejects_malformed_list_items_without_panicking() {
        // Regression: malformed list-item lines must return an error, never panic.
        for content in [
            "character:\n- \n",
            "character:\n- abc\n",
            "character:\n-\n",
            "character:\n-\n- 200001\n",
        ] {
            assert!(parse_max_data(content).is_err(), "content: {content:?}");
        }
    }

    #[test]
    fn bundled_mod_settings_deserializes() {
        let bundled: ModSettings =
            serde_json::from_str(include_str!("../liqi_config/settings.mod.json")).unwrap();
        // This is a user-editable file; the selected character is not fixed.
        ModSettings::default_avatar_id(bundled.main_char).unwrap();
        assert!(!bundled.char_skin.is_empty());
    }

    #[test]
    fn partial_mod_settings_keeps_known_fields_and_defaults_the_rest() {
        // Regression: 无 serde(default) 时缺任一字段都会整体解析失败，
        // 进而被默认值覆写 —— 用户配置被静默清空。
        // 顺带覆盖：旧版遗留的 version / autoUpdate 键应被忽略而非报错。
        let json = r#"{
            "mainChar": 200042,
            "nickname": "雀魂",
            "version": "v0.11.252.w",
            "autoUpdate": true
        }"#;

        let settings: ModSettings = serde_json::from_str(json).unwrap();
        assert_eq!(settings.main_char, 200042);
        assert_eq!(settings.nickname, "雀魂");
        // 未提供的字段回退到默认值，而不是整个配置被重置
        assert!(settings.hint_on());
        assert!(settings.show_server());
        assert_eq!(settings.preset_index, 0);
    }

    #[test]
    fn derives_default_avatar_id_for_both_id_widths() {
        // 6 位和 8 位角色 ID 都存在于 max_data.yaml，规则是取第 5 位起的后缀
        assert_eq!(ModSettings::default_avatar_id(200001).unwrap(), 400101);
        assert_eq!(ModSettings::default_avatar_id(200042).unwrap(), 404201);
        assert_eq!(ModSettings::default_avatar_id(20000125).unwrap(), 40012501);
    }

    #[test]
    fn every_bundled_character_has_a_default_avatar_id() {
        let data = parse_max_data(include_str!("../liqi_config/max_data.yaml")).unwrap();
        for char_id in data.character {
            ModSettings::default_avatar_id(char_id)
                .unwrap_or_else(|e| panic!("角色 {char_id} 推导默认装扮失败: {e}"));
        }
    }

    #[test]
    fn avatar_id_falls_back_when_char_skin_missing() {
        // Regression: char_skin 是惰性填充的，缺失时不得 panic
        let mut settings = ModSettings::default();
        assert!(settings.char_skin.is_empty());
        assert_eq!(settings.main_avatar_id().unwrap(), 400101);

        settings.char_skin.insert(200001, 400199);
        assert_eq!(settings.main_avatar_id().unwrap(), 400199);
    }

    #[test]
    fn out_of_range_preset_index_falls_back_to_first() {
        // Regression: preset_index 来自客户端，越界时不得索引定长数组 panic
        let mut settings = ModSettings::default();
        settings.views_presets[0] = vec![ViewSlot {
            slot: 5,
            r#type: 0,
            item_id: 305519,
            item_id_list: vec![],
        }];

        settings.preset_index = 0;
        assert_eq!(settings.avatar_frame(), 305519);

        settings.preset_index = 9999;
        assert_eq!(settings.current_preset().len(), 1);
        assert_eq!(settings.avatar_frame(), 305519);
    }

    #[test]
    fn generates_rpc_map_from_bundled_descriptor() {
        let json = generate_liqi_json(include_bytes!("../liqi_config/liqi.desc")).unwrap();
        let map: Value = serde_json::from_str(&json).unwrap();
        let auth_game = &map[".lq.FastTest.authGame"];

        assert_eq!(auth_game["req"], ".lq.ReqAuthGame");
        assert_eq!(auth_game["resp"], ".lq.ResAuthGame");
    }
}

#[derive(Serialize, Deserialize, Debug, Clone)]
// serde(default) 不可省略：缺字段会让反序列化整体失败，
// 而失败分支会用默认值覆写用户的 settings.mod.json，等于静默清空全部配置。
// 有了它，新增/删除字段才不会波及既有用户。
#[serde(rename_all = "camelCase", default)]
pub struct ModSettings {
    pub main_char: u32,
    pub char_skin: HashMap<u32, u32>,
    pub nickname: String,
    pub star_character: Vec<u32>,
    pub hidden_characters: Vec<u32>,
    hint_switch: bool,
    pub title: u32,
    pub loading_bg: Vec<u32>,
    emoji_switch: bool,
    pub views_presets: [Vec<ViewSlot>; 10],
    pub preset_index: u32,
    show_server: bool,
    anti_nickname_censorship: bool,
    pub random_char_switch: bool,
    pub random_char_pool: Vec<(u32, u32)>,
    pub verified: u32,
    #[serde(skip)]
    dir: PathBuf,
}

impl Default for ModSettings {
    fn default() -> Self {
        Self {
            main_char: 200001,
            char_skin: Default::default(),
            nickname: String::new(),
            star_character: Vec::new(),
            hidden_characters: Vec::new(),
            hint_switch: true,
            title: 0,
            loading_bg: Vec::new(),
            emoji_switch: false,
            views_presets: Default::default(),
            preset_index: 0,
            show_server: true,
            anti_nickname_censorship: true,
            random_char_switch: false,
            random_char_pool: Vec::new(),
            verified: 0,
            dir: PathBuf::new(),
        }
    }
}

impl ModSettings {
    pub fn new(general_settings: &Settings) -> Result<Self> {
        let dir = general_settings.data_dir().join("settings.mod.json");
        let mut settings: Self = match std::fs::read_to_string(&dir) {
            Ok(content) => serde_json::from_str(&content).context("无法解析settings.mod.json")?,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                let default = Self {
                    dir: general_settings.data_dir().to_path_buf(),
                    ..Default::default()
                };
                default.write();
                return Ok(default);
            }
            Err(error) => return Err(error).context("无法读取settings.mod.json"),
        };
        settings.dir = general_settings.data_dir().to_path_buf();
        Ok(settings)
    }

    /// 角色的默认装扮 ID，规则为 `40{角色号第 5 位起}01`（如 200001 -> 400101，
    /// 20000125 -> 40012501）。
    ///
    /// 必须与 `Modder::perfect_character` 往 `char_skin` 里写入的规则保持一致。
    pub fn default_avatar_id(char_id: u32) -> Result<u32> {
        let id_str = char_id.to_string();
        let slice = id_str
            .get(4..)
            .with_context(|| format!("角色 ID {char_id} 过短，无法推导默认装扮"))?;
        format!("40{slice}01")
            .parse()
            .with_context(|| format!("无法解析角色 {char_id} 的默认装扮 ID"))
    }

    /// 角色当前的装扮 ID。
    ///
    /// `char_skin` 是惰性填充的（只有 `perfect_character` 和 `changeCharacterSkin`
    /// 会写入），所以任何时候都可能缺少某个角色的条目 —— 典型场景是全新安装尚未
    /// 拉取过角色列表。缺失时退回默认装扮，绝不 panic。
    pub fn avatar_id_of(&self, char_id: u32) -> Result<u32> {
        match self.char_skin.get(&char_id) {
            Some(skin) => Ok(*skin),
            None => Self::default_avatar_id(char_id),
        }
    }

    /// 主角色当前的装扮 ID。
    pub fn main_avatar_id(&self) -> Result<u32> {
        self.avatar_id_of(self.main_char)
    }

    /// 当前生效的装扮预设。
    ///
    /// `preset_index` 直接来自客户端的 `useCommonView` / `saveCommonViews` 消息，
    /// 越界时退回 0 号预设，避免索引定长数组导致 panic。
    pub fn current_preset(&self) -> &[ViewSlot] {
        self.views_presets
            .get(self.preset_index as usize)
            .unwrap_or(&self.views_presets[0])
    }

    /// 当前生效预设里的头像框（`slot == 5`）道具 ID。
    pub fn avatar_frame(&self) -> u32 {
        self.current_preset()
            .iter()
            .find(|v| v.slot == 5)
            .map(|v| v.item_id)
            .unwrap_or_default()
    }

    /// 装扮预设槽位数量。
    pub fn preset_count(&self) -> usize {
        self.views_presets.len()
    }

    pub fn hint_on(&self) -> bool {
        self.hint_switch
    }
    pub fn emoji_on(&self) -> bool {
        self.emoji_switch
    }
    pub fn show_server(&self) -> bool {
        self.show_server
    }
    pub fn anti_nickname_censorship(&self) -> bool {
        self.anti_nickname_censorship
    }

    pub fn write(&self) {
        let dir = self.dir.join("settings.mod.json");
        let Ok(content) = serde_json::to_string_pretty(self) else {
            error!("Failed to serialize settings.mod.json");
            return;
        };
        // The JSONL worker processes requests in order. Commit each small snapshot
        // before replying so rapid selections and shutdown cannot reorder saves.
        let temporary = self.dir.join("settings.mod.json.tmp");
        if std::fs::write(&temporary, content)
            .and_then(|_| std::fs::rename(&temporary, &dir)).is_err() {
            error!("Failed to write settings.mod.json");
        }
    }
}
