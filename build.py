"""Build a minimal add-on package from an explicit allowlist."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent
FILES = ["__init__.py", "ui.py", "statistics_integration.py", "core/__init__.py", "core/service.py", "manifest.json", "config.json", "LICENSE"]

def build():
    for name in FILES:
        if not (ROOT / name).is_file():
            raise SystemExit(f"Missing required file: {name}")
    output = ROOT / "AnkiDeckArchive.ankiaddon"
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(ROOT / name, name)
    with ZipFile(output) as archive:
        if set(archive.namelist()) != set(FILES) or archive.testzip():
            raise SystemExit("Package validation failed")
    print(output)

if __name__ == "__main__":
    build()
