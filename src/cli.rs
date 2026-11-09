use clap::Parser;
use std::path::PathBuf;

#[derive(Parser, Debug)]
#[command(
    name = "akagiplus",
    about = "AkagiPlus - Mahjong AI and local cosmetics"
)]
pub struct Cli {
    #[arg(short, long, help = "Path to config.toml")]
    pub config: Option<PathBuf>,
}
