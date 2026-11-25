"""Generate, post-process and install differentiated sprites for the 3 forms.

Stages (all outputs go to art_work/ first; nothing in the form folders is
touched until ``install``, which backs the old art up to art_backup/):

    py -3.13 tools/sprite_gen/gen.py probe
    py -3.13 tools/sprite_gen/gen.py concept --form carbon --n 2
    py -3.13 tools/sprite_gen/gen.py frames --form carbon [--assets idle_front,happy] [--jobs 4]
    py -3.13 tools/sprite_gen/gen.py process --form carbon
    py -3.13 tools/sprite_gen/gen.py install --form carbon
    py -3.13 tools/sprite_gen/gen.py icon

The API key is read from OPENAI_API_KEY, else D:/agy-pet/gpt-key.key, else
~/.agy-pet/image_api.key.  It is never printed or written anywhere.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures as cf
import io
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spec import ASSETS, DOCK_ASSETS, DOCK_STYLE, FORMS, MIRRORS, SKIP_REGENERATE, DROP_FIRST, KEEP_FRAMES, STYLE, poses  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "art_work"
BACKUP = ROOT / "art_backup"
HEIGHTS = (187, 238, 306)
API = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
MODEL_CANDIDATES = [m for m in (os.environ.get("AGY_IMAGE_MODEL"),) if m] + [
    "gpt-image-2.6", "gpt-image-2.5-flare", "gpt-image-2.5", "gpt-image-2.5-sunburst", "gpt-image-2", "gpt-image-1.5", "gpt-image-1",
]
MODEL_FILE = WORK / "model.json"


# ----- API ----------------------------------------------------------------------------

def api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    for path in (ROOT / "gpt-key.key", Path.home() / ".agy-pet" / "image_api.key"):
        if not key and path.is_file():
            key = path.read_text(encoding="utf-8-sig").strip()
    if not key:
        sys.exit("没有找到 API key（OPENAI_API_KEY 或 gpt-key.key）")
    return key


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.message = message


def _post(path: str, body: bytes, content_type: str, timeout: float = 300) -> dict:
    request = urllib.request.Request(
        f"{API}{path}", data=body, method="POST",
        headers={"Authorization": f"Bearer {api_key()}", "Content-Type": content_type},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", "replace")
        try:
            message = json.loads(raw)["error"]["message"]
        except Exception:
            message = raw[:400]
        raise ApiError(error.code, message) from None


def _multipart(fields: dict[str, str], files: list[tuple[str, str, bytes]]) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    out = io.BytesIO()
    for name, value in fields.items():
        out.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    for name, filename, data in files:
        out.write(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\n"
            "Content-Type: image/png\r\n\r\n".encode()
        )
        out.write(data)
        out.write(b"\r\n")
    out.write(f"--{boundary}--\r\n".encode())
    return out.getvalue(), f"multipart/form-data; boundary={boundary}"


def model() -> str:
    if MODEL_FILE.is_file():
        return json.loads(MODEL_FILE.read_text())["model"]
    sys.exit("先运行 probe 选出可用模型")


def generate(prompt: str, size: str, quality: str, n: int = 1) -> list[bytes]:
    body = json.dumps({
        "model": model(), "prompt": prompt, "size": size, "quality": quality, "n": n,
        "background": "transparent", "output_format": "png",
    }).encode()
    data = _post("/images/generations", body, "application/json")
    return [base64.b64decode(item["b64_json"]) for item in data["data"]]


def edit(prompt: str, refs: list[Path], size: str, quality: str) -> bytes:
    fields = {"model": model(), "prompt": prompt, "size": size, "quality": quality,
              "background": "transparent", "output_format": "png", "input_fidelity": "high"}
    files = [("image[]", p.name, p.read_bytes()) for p in refs]
    for attempt in range(2):
        body, ctype = _multipart(fields, files)
        try:
            data = _post("/images/edits", body, ctype)
            return base64.b64decode(data["data"][0]["b64_json"])
        except ApiError as error:
            if attempt == 0 and "input_fidelity" in error.message:
                fields.pop("input_fidelity")
                continue
            raise
    raise RuntimeError("unreachable")


def with_retry(fn, *args, tries: int = 8):
    for attempt in range(tries):
        try:
            return fn(*args)
        except ApiError as error:
            if error.status in (400, 401, 403, 404) or attempt == tries - 1:
                raise
            if error.status == 429:  # per-minute input-image quota
                time.sleep(15 + 5 * attempt)
                continue
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == tries - 1:
                raise
        time.sleep(4 * (attempt + 1))


# ----- commands -----------------------------------------------------------------------

def cmd_probe(_args) -> None:
    WORK.mkdir(exist_ok=True)
    for name in MODEL_CANDIDATES:
        body = json.dumps({"model": name, "prompt": "a small blue star sticker", "size": "1024x1024",
                           "quality": "low", "background": "transparent", "output_format": "png"}).encode()
        try:
            data = _post("/images/generations", body, "application/json", timeout=180)
        except ApiError as error:
            print(f"{name}: 不可用（{error.status} {error.message[:140]}）")
            continue
        png = base64.b64decode(data["data"][0]["b64_json"])
        alpha = Image.open(io.BytesIO(png)).convert("RGBA").getchannel("A").getextrema()
        (WORK / "probe.png").write_bytes(png)
        MODEL_FILE.write_text(json.dumps({"model": name}))
        print(f"{name}: 可用，透明背景 alpha 范围 {alpha}")
        return
    sys.exit("没有可用的生图模型")


def character_prompt(form: str, *, asset: str = "") -> str:
    spec = FORMS[form]
    style = DOCK_STYLE if asset in DOCK_ASSETS else STYLE
    return f"{style}\nCharacter: {spec['character']}\nBody language: {spec['body_language']}."


def cmd_concept(args) -> None:
    out = WORK / args.form / "concept"
    out.mkdir(parents=True, exist_ok=True)
    prompt = character_prompt(args.form) + "\nPose: standing relaxed, facing the viewer, neutral pose that shows the whole outfit clearly."
    images = with_retry(generate, prompt, "1024x1536", args.quality, args.n)
    start = len(list(out.glob("concept_*.png")))
    for i, png in enumerate(images):
        path = out / f"concept_{start + i:02d}.png"
        path.write_bytes(png)
        print(path)


def reference(form: str) -> Path:
    """The original catgirl design: the form's existing front idle master."""
    path = WORK / form / "reference.png"
    if not path.is_file():
        original = ROOT / form / "processed" / "masters" / "generated" / "idle_front.png"
        if not original.is_file():
            sys.exit(f"找不到 {original}")
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, path)
    return path


def _frame_job(form: str, asset: str, index: int, size: str, pose: str, quality: str) -> Path:
    out = WORK / form / "raw" / asset / f"{index:02d}.png"
    if out.is_file():
        return out
    refs = [reference(form)]
    first = WORK / form / "raw" / asset / "00.png"
    if index > 0 and first.is_file():
        refs.append(first)
        lead = ("Image 1 is the character reference. Image 2 is frame 1 of this animation: keep the exact same character, "
                "outfit, colours, scale, camera and framing as image 2, and change only what this frame describes.")
    else:
        lead = "Image 1 is the character reference: keep her design, outfit, colours and proportions exactly."
    prompt = f"{lead}\n{character_prompt(form, asset=asset)}\nThis frame: {pose}."
    png = with_retry(edit, prompt, refs, size, quality)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    return out


def cmd_frames(args) -> None:
    reference(args.form)
    raw_assets = args.assets.split(",") if args.assets else [a for a in ASSETS if a not in SKIP_REGENERATE]
    assets: list[str] = []
    unknown: list[str] = []
    for a in raw_assets:
        src = MIRRORS.get(a, a)
        if src not in ASSETS:
            unknown.append(a)
        elif src not in assets:
            assets.append(src)
    if unknown:
        sys.exit(f"未知 asset：{unknown}")
    # Frame 0 of every asset first (later frames reference it), then the rest.
    waves = [[(a, 0) for a in assets], [(a, i) for a in assets for i in range(1, len(ASSETS[a][1]))]]
    failures = []
    with cf.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for wave in waves:
            futures = {
                pool.submit(_frame_job, args.form, a, i, ASSETS[a][0], poses(args.form, a)[i], args.quality): (a, i)
                for a, i in wave
            }
            for future in cf.as_completed(futures):
                a, i = futures[future]
                try:
                    print("ok", future.result().relative_to(ROOT), flush=True)
                except Exception as error:  # keep going; rerun fills the gaps
                    failures.append((a, i, str(error)[:200]))
                    print("FAIL", a, i, str(error)[:200], flush=True)
    print(f"完成，失败 {len(failures)} 帧" + ("（重新运行同一命令会只补缺的帧）" if failures else ""))


def _clean_alpha(image: Image.Image) -> Image.Image:
    image = image.convert("RGBA")
    alpha = image.getchannel("A").point(lambda v: 0 if v < 12 else v)
    image.putalpha(alpha)
    return image


def cmd_process(args) -> None:
    form = args.form
    requested = set(args.assets.split(",")) if getattr(args, "assets", None) else None
    stage = WORK / form / ("processed_partial" if requested else "processed")
    if requested and stage.exists():
        shutil.rmtree(stage)
    manifest_assets: dict[str, dict] = {}
    for asset in list(ASSETS) + list(MIRRORS):
        source = MIRRORS.get(asset, asset)
        if requested and asset not in requested and source not in requested:
            continue
        raws = sorted((WORK / form / "raw" / source).glob("*.png"))
        if len(raws) != len(ASSETS[source][1]):
            if source not in SKIP_REGENERATE:
                print(f"跳过 {asset}：帧不全（{len(raws)}/{len(ASSETS[source][1])}）")
            continue
        if source in DROP_FIRST:
            raws = raws[1:]
        if source in KEEP_FRAMES:
            raws = raws[: KEEP_FRAMES[source]]
        frames = [_clean_alpha(Image.open(p)) for p in raws]
        if asset in MIRRORS:
            frames = [f.transpose(Image.Transpose.FLIP_LEFT_RIGHT) for f in frames]
        # One union box per animation keeps relative motion and a stable scale.
        boxes = [f.getchannel("A").getbbox() for f in frames]
        boxes = [b for b in boxes if b]
        union = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
        crops = [f.crop(union) for f in frames]
        multi = len(crops) > 1
        entry = {"source_masters": [], "frames": {str(h): [] for h in HEIGHTS}, "frame_count": len(crops)}
        for i, crop in enumerate(crops):
            suffix = f"_{i:02d}" if multi else ""
            master = stage / "masters" / "generated" / f"{asset}{suffix}.png"
            master.parent.mkdir(parents=True, exist_ok=True)
            crop.save(master)
            entry["source_masters"].append(f"assets/processed/masters/generated/{asset}{suffix}.png")
            scale_ratio = 0.81 if source in DOCK_ASSETS else 1.0
            for h in HEIGHTS:
                target_h = max(1, round(h * scale_ratio))
                w = max(1, round(crop.width * target_h / crop.height))
                out = stage / "runtime" / "states" / asset / f"{asset}_{h}{suffix}.png"
                out.parent.mkdir(parents=True, exist_ok=True)
                crop.resize((w, target_h), Image.Resampling.LANCZOS).save(out, optimize=True)
                entry["frames"][str(h)].append(f"assets/processed/runtime/states/{asset}/{asset}_{h}{suffix}.png")
        manifest_assets[asset] = entry
    character_id = "hydrogen" if form == "hydergon" else form
    manifest = {"format_version": 4, "character_id": character_id, "assets": manifest_assets}
    manifest_name = "actions_partial.json" if requested else "actions.json"
    (WORK / form / manifest_name).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{form}：处理了 {len(manifest_assets)} 个 asset → {stage}")


def cmd_install(args) -> None:
    form = args.form
    partial_mode = bool(getattr(args, "partial_stage", False))
    staged = WORK / form / ("processed_partial" if partial_mode else "processed")
    manifest = WORK / form / ("actions_partial.json" if partial_mode else "actions.json")
    if not staged.is_dir() or not manifest.is_file():
        sys.exit("先运行 process")
    target = ROOT / form
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = BACKUP / f"{form}-{stamp}"
    old_manifest = target / "manifests" / "actions.json"
    if old_manifest.is_file():
        if not partial_mode:
            shutil.copytree(target, backup)
        else:
            backup = None
        old = json.loads(old_manifest.read_text(encoding="utf-8"))
    else:  # brand-new form
        (target / "manifests").mkdir(parents=True, exist_ok=True)
        old = {"format_version": 4, "character_id": form, "assets": {}}
        backup = None
    new = json.loads(manifest.read_text(encoding="utf-8"))
    missing = sorted(set(old["assets"]) - set(new["assets"]) - SKIP_REGENERATE)
    if missing and not args.allow_partial and not partial_mode:
        sys.exit(f"新素材缺少 {missing}，加 --allow-partial 会保留这些旧素材")
    for key in set(old["assets"]) - set(new["assets"]):
        new["assets"][key] = old["assets"][key]
    new = {**old, "assets": {**new["assets"]}}  # keep format_version and other top-level keys
    shutil.copytree(staged, target / "processed", dirs_exist_ok=True)
    (target / "manifests" / "actions.json").write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已安装到 {target}" + (f"，旧素材备份在 {backup}" if backup else "（增量合入）"))


def cmd_icon(args) -> None:
    out = WORK / "icon"
    out.mkdir(parents=True, exist_ok=True)
    refs = [reference(form) for form in ("carbon", "hydergon", "neon")]
    prompt = (
        "App icon for a desktop pet app. Use the three catgirls from the reference images, keeping their exact designs and art style: "
        "image 1 the black-haired red-eyed gothic catgirl, image 2 the white-and-sky-blue haired catgirl, image 3 the violet-haired neon catgirl. "
        "Show their three chibi faces close together inside one circular badge, image 2 in the middle slightly higher. "
        "Bold simple shapes readable at 32x32 pixels, thick clean outlines, dark navy circular background with a subtle orbit ring and a few small stars, "
        "no text, centered, transparent outside the circle."
    )
    start = len(list(out.glob("icon_*.png")))
    for i in range(args.n):
        png = with_retry(edit, prompt, refs, "1024x1024", args.quality)
        path = out / f"icon_{start + i:02d}.png"
        path.write_bytes(png)
        print(path)


def cmd_make_ico(args) -> None:
    source = Path(args.source)
    image = _clean_alpha(Image.open(source))
    box = image.getchannel("A").getbbox()
    image = image.crop(box)
    side = max(image.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
    shutil.copy2(ROOT / "icon.ico", WORK / f"icon-backup-{time.strftime('%Y%m%d-%H%M%S')}.ico")
    square.resize((256, 256), Image.Resampling.LANCZOS).save(
        ROOT / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    )
    print("icon.ico 已更新")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe")
    p = sub.add_parser("concept"); p.add_argument("--form", choices=FORMS, required=True); p.add_argument("--n", type=int, default=2); p.add_argument("--quality", default="high")
    p = sub.add_parser("frames"); p.add_argument("--form", choices=FORMS, required=True); p.add_argument("--assets"); p.add_argument("--jobs", type=int, default=4); p.add_argument("--quality", default="medium")
    p = sub.add_parser("process"); p.add_argument("--form", choices=FORMS, required=True); p.add_argument("--assets")
    p = sub.add_parser("install"); p.add_argument("--form", choices=FORMS, required=True); p.add_argument("--allow-partial", action="store_true"); p.add_argument("--partial-stage", action="store_true")
    p = sub.add_parser("icon"); p.add_argument("--n", type=int, default=2); p.add_argument("--quality", default="high")
    p = sub.add_parser("make-ico"); p.add_argument("source")
    args = parser.parse_args()
    {"probe": cmd_probe, "concept": cmd_concept, "frames": cmd_frames, "process": cmd_process,
     "install": cmd_install, "icon": cmd_icon, "make-ico": cmd_make_ico}[args.cmd](args)


if __name__ == "__main__":
    main()
