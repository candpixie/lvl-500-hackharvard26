"""Container image for the ask reasoner: pipeline code, ask_core and the data files. No decorators; importing deploys nothing.

Deliberately does not import chalk_tools.core (that needs pandas, which the light scorer image lacks).
Files use strategy "volume" so building this object inside a Chalk container, where the local paths do not exist,
does not try to read them; "copy" would.
"""
from pathlib import Path

from chalkcompute import Image

ROOT = Path(__file__).resolve().parent.parent
DATA = {  # local file -> path inside the container
    ROOT / "data/out/shells.json": "/app/data/shells.json",
    ROOT / "data/out/close_approaches.json": "/app/data/close_approaches.json",
    ROOT / "data/out/tools/catalog.csv.gz": "/app/data/catalog.csv.gz",
}
CODE = {
    ROOT / "pipeline/orbit_data.py": "/app/pipeline/orbit_data.py",
    ROOT / "pipeline/scoring.py": "/app/pipeline/scoring.py",
    ROOT / "chalk_tools/ask_core.py": "/app/ask_core.py",
    ROOT / "chalk_tools/ask_app.py": "/app/app.py",
}


def build_image(code_strategy: str = "copy", entrypoint: bool = True):
    img = (Image.debian_slim("3.12").pip_install(["flask", "numpy", "pandas", "chalkcompute", "opentelemetry-sdk", "opentelemetry-exporter-otlp"])
           .env({"ASK_PIPELINE": "/app/pipeline", "ASK_DATA": "/app/data", "PYTHONUNBUFFERED": "1"}))
    # Inside a Chalk container these local paths do not exist and the image object is unused, so skip missing files.
    for src, dst in CODE.items():
        if src.exists():
            img = img.add_local_file(str(src), dst, strategy=code_strategy)
    for src, dst in DATA.items():
        if src.exists():
            img = img.add_local_file(str(src), dst, strategy="volume")
    img = img.workdir("/app")
    return img.entrypoint(["python", "/app/app.py"]) if entrypoint else img


LIGHT_IMAGE = Image.debian_slim("3.12")  # scorers: pure Python, no data
