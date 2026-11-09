"""Public data stays read-only; all personal choices live outside the source."""
import os
from pathlib import Path
MAJSOULMAX = Path(__file__).resolve().parent
PROTO = MAJSOULMAX / 'proto'
DATA = MAJSOULMAX / 'config'
# Required explicitly: never fall back to an original Akagi/Copilot profile.
CONFIG = Path(os.environ['AKAGIPLUS_MAJSOULMAX_DATA_DIR']).resolve()
CONFIG.mkdir(parents=True, exist_ok=True)
