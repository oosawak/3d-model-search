#!/usr/bin/env python3
"""Polyfork + Sand3D の統合索引を作る（試作版）。

出所:
- Polyfork: ローカルの fork の catalog.json（全件、サムネイルURLつき）
- Sand3D: Hugging Face datasets-server の rows API からサンプル取得
  （render 画像URL、family=カテゴリ、entry/attribution=名前、license）
"""
import json
import re
import subprocess
import time
from pathlib import Path

OUT = Path(__file__).parent / "index.json"
POLYFORK_CATALOG = Path.home() / "workspace/polyfork-catalog/catalog.json"

# Sand3D: データセットごとに何件サンプルするか（試作版）
SAND3D_SAMPLES = {
    "sand3d-objaverse": 600,
    "sand3d-cad": 100,
    "sand3d-articraft": 100,
    "sand3d-simready": 100,
    "sand3d-automate": 100,
}


def polyfork_items():
    d = json.loads(POLYFORK_CATALOG.read_text())
    kit_title = {k["id"]: k["title"] for k in d.get("kits", [])}
    items = []
    for a in d["assets"]:
        items.append({
            "name": a["title"],
            "cat": a.get("type", ""),
            "sub": kit_title.get(a.get("kit", ""), ""),
            "src": "Polyfork",
            "format": "GLB",
            "img": a["thumbnail"],
            "link": a["page"],
            "dl": a.get("glb", ""),
            "lic": "CC BY 4.0 / Polyfork license (per model)",
            "credit": "Polyfork",
        })
    return items


def fetch_rows(dataset, want):
    rows = []
    offset = 0
    while len(rows) < want:
        n = min(100, want - len(rows))
        url = ("https://datasets-server.huggingface.co/rows"
               f"?dataset=Sandflow%2F{dataset}&config=default&split=train"
               f"&offset={offset}&length={n}")
        try:
            p = subprocess.run(
                ["curl", "-s", "--max-time", "120", url],
                capture_output=True, text=True, timeout=150)
            data = json.loads(p.stdout)
        except Exception as e:
            print(f"  {dataset}: offset {offset} 取得失敗: {e}")
            break
        got = data.get("rows", [])
        if not got:
            break
        rows.extend(got)
        offset += len(got)
        time.sleep(0.3)
    return rows


def _sniff_ext(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ""


THUMB_DIR = Path(__file__).parent / "sand-thumbs"


def localize_render(src_url: str, ds: str, idx: int) -> str:
    """署名付きURLは数時間で失効するため、render画像を自前で保持する。"""
    if not src_url:
        return ""
    THUMB_DIR.mkdir(exist_ok=True)
    stem = f"{ds.replace('sand3d-', '')}-{idx:04d}"
    for ext in (".jpg", ".png", ".webp"):
        if (THUMB_DIR / (stem + ext)).exists():
            return f"sand-thumbs/{stem}{ext}"
    for attempt in range(2):
        p = subprocess.run(["curl", "-s", "--max-time", "60", src_url],
                           capture_output=True, timeout=90)
        data = p.stdout or b""
        ext = _sniff_ext(data)
        if ext:
            (THUMB_DIR / (stem + ext)).write_bytes(data)
            return f"sand-thumbs/{stem}{ext}"
        time.sleep(1)
    print(f"  render取得失敗: {ds} #{idx}")
    return ""


def sand3d_items():
    from concurrent.futures import ThreadPoolExecutor
    items = []
    for ds, want in SAND3D_SAMPLES.items():
        print(f"Sand3D {ds}: {want} 件取得中...")
        rows = fetch_rows(ds, want)
        print(f"  -> {len(rows)} 件")
        ds_items = []
        jobs = []
        for i, r in enumerate(rows):
            row = r["row"]
            attr = row.get("attribution") or ""
            m = re.match(r'"([^"]+)"', attr)
            name = m.group(1) if m else (row.get("entry") or row["id"]).replace("_", " ")
            render = row.get("render") or {}
            ds_items.append({
                "name": name,
                "cat": row.get("family", ""),
                "sub": row.get("entry", ""),
                "src": f"Sand3D {ds.replace('sand3d-', '')}",
                "format": "Python code",
                "img": "",
                "link": f"https://huggingface.co/datasets/Sandflow/{ds}",
                "dl": "",
                "lic": row.get("license", ""),
                "credit": (row.get("attribution") or "").strip()[:200],
                "joints": row.get("n_joints", 0),
            })
            jobs.append((render.get("src", ""), ds, i))
        with ThreadPoolExecutor(max_workers=8) as ex:
            for it, local in zip(ds_items, ex.map(lambda j: localize_render(*j), jobs)):
                it["img"] = local
        ok = sum(1 for it in ds_items if it["img"])
        print(f"  render自前化: {ok}/{len(ds_items)} 件")
        items += ds_items
    return items


ABO_DIR = Path(__file__).parent / "abo"
S3 = "https://amazon-berkeley-objects.s3.amazonaws.com"


def _pick_lang(arr, prefer=("en-US", "en-GB", "en")):
    if not arr:
        return ""
    for p in prefer:
        for e in arr:
            if isinstance(e, dict) and e.get("language_tag") == p:
                return e.get("value", "")
    for e in arr:
        if isinstance(e, dict) and (e.get("language_tag") or "").startswith("en"):
            return e.get("value", "")
    e = arr[0]
    return e.get("value", "") if isinstance(e, dict) else str(e)


def abo_items():
    import csv
    import gzip
    import io

    img_path = {}
    with gzip.open(ABO_DIR / "images.csv.gz", "rt") as f:
        for r in csv.DictReader(f):
            img_path[r["image_id"]] = r["path"]

    models = {}
    with gzip.open(ABO_DIR / "3dmodels.csv.gz", "rt") as f:
        for r in csv.DictReader(f):
            models[r["3dmodel_id"]] = r["path"]

    listings = {}
    for shard in sorted(ABO_DIR.glob("listings_*.json.gz")):
        with gzip.open(shard, "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                mid = d.get("3dmodel_id")
                if mid and mid in models:
                    listings[mid] = d

    items = []
    for mid, path in models.items():
        d = listings.get(mid, {})
        name = _pick_lang(d.get("item_name")) or mid
        ptype = ""
        pt = d.get("product_type") or []
        if pt and isinstance(pt[0], dict):
            ptype = pt[0].get("value", "")
        img = ""
        iid = d.get("main_image_id")
        if iid and iid in img_path:
            img = f"{S3}/images/small/{img_path[iid]}"
        items.append({
            "name": name,
            "cat": ptype,
            "sub": _pick_lang(d.get("brand")),
            "src": "ABO",
            "format": "glTF",
            "img": img,
            "link": f"{S3}/index.html",
            "dl": f"{S3}/3dmodels/original/{path}",
            "lic": "CC BY 4.0",
            "credit": "Amazon Berkeley Objects (ABO) dataset",
        })
    return items


def main():
    items = polyfork_items()
    print(f"Polyfork: {len(items)} 件")
    items += sand3d_items()
    abo = abo_items()
    print(f"ABO: {len(abo)} 件")
    items += abo
    OUT.write_text(json.dumps(items, ensure_ascii=False))
    print(f"合計 {len(items)} 件 -> {OUT}")


if __name__ == "__main__":
    main()
