from pathlib import Path

from rrr_agent.client import RrrApiError, RrrClient
from rrr_agent.config import load_settings
from rrr_agent.preke import load_draft, save_draft
from rrr_agent.skelbimai import apply_public_photos, local_photo_files, upload_draft
from rrr_agent.viesos import temporary_public_base

folder = Path("prekes/partijos/20261110-171412")
path = folder / "01-land-rover-defender-1997.json"
draft = load_draft(path)
draft["detale"].pop("ovoko_id", None)
# Restore a local photo path so the tunnel can serve it.
name = "a53e20e6709a488eb189b0a1e9990d2d.jpg"
draft["detale"]["photo"] = f"/nuotraukos/{name}"
draft["detale"]["photos"] = [f"/nuotraukos/{name}"]
save_draft(path, draft)

with temporary_public_base(local_photo_files([draft])) as base:
    print("base", base, flush=True)
    apply_public_photos(draft, base or "")
    save_draft(path, draft)
    client = RrrClient(load_settings())
    try:
        result = upload_draft(path, client)
        print("ok", result.get("part_id"), result.get("perspejimas", ""), flush=True)
    except RrrApiError as exc:
        print("klaida", exc, flush=True)
    print("hitai", list(getattr(temporary_public_base, "hits", [])), flush=True)
