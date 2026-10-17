"""Image and data loading shared by the Chalk function modules. No decorators here, so importing it deploys nothing."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from chalkcompute import Image

from chalk_tools import core

LOCAL_TOOLS_DIR = core.ROOT / "data/out/tools"
REMOTE_TOOLS_DIR = "/app/tools_data"

IMAGE = (
    Image.debian_slim("3.12")
    .pip_install(["pandas", "numpy"])
    .add_local_dir(str(LOCAL_TOOLS_DIR), REMOTE_TOOLS_DIR, strategy="volume")  # "copy" caps files at 32 KiB
)


@lru_cache(maxsize=1)
def snapshot() -> core.Snapshot:
    """Loaded once per container; the remote image has the data at REMOTE_TOOLS_DIR."""
    remote = Path(REMOTE_TOOLS_DIR)
    return core.Snapshot.load_compact(remote if remote.exists() else LOCAL_TOOLS_DIR)
