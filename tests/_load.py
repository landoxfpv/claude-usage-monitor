import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_kiosk():
    spec = importlib.util.spec_from_file_location(
        "kiosk_fb", ROOT / "pi" / "kiosk-fb.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
