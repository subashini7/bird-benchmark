"""
Full rebuild: re-selects, applies first-session corrections, adds 50 confusing images,
and produces correctly-labeled images/ + labels.csv + slideshow.

Run this instead of create_images_dataset.py + add_confusing_images.py.
"""

import csv, re, os, shutil, random, json
from collections import defaultdict
import osxphotos

IMAGES_DIR = "images"
LABELS_CSV = "labels.csv"
SLIDESHOW  = "review_slideshow.html"

REGION_CONFIG = {
    "India":     ("India_classified_birds_report_20260602_180920.csv",     0.31),
    "Singapore": ("Singapore_classified_birds_report_20260602_070959.csv", 0.40),
    "UK":        ("UK_classified_birds_report_20260602_090847.csv",        0.31),
    "US":        ("US_classified_birds_report_20260602_093211.csv",        0.99),
}
REGION_QUOTA = {"India": 30, "Singapore": 25, "UK": 15, "US": 30}

# ── First-session manual corrections (by original image_001-100 numbering) ──
FIRST_SESSION_CORRECTIONS = {
    "image_007.jpg": {"num_birds": "2", "common_name": "Asian Openbill / Painted Stork"},
    "image_009.jpg": {"common_name": "Gray Heron / Asian Openbill"},
    "image_052.jpg": {"num_birds": "1"},
    "image_057.jpg": {"num_birds": "2"},
    "image_066.jpg": {"num_birds": "1"},
    "image_073.jpg": {"num_birds": "1"},
    "image_077.jpg": {"common_name": "American Kestrel"},
    "image_078.jpg": {"common_name": "American Kestrel"},
    "image_080.jpg": {"common_name": "American Robin"},
    "image_083.jpg": {"common_name": "American Wigeon"},
    "image_089.jpg": {"num_birds": "1"},
}
FIRST_SESSION_REMOVE = {"image_070.jpg", "image_088.jpg"}

# ── Post-rebuild corrections (by final post-shuffle image_XXX numbering) ─────
# Applied after images are copied and numbered; seed=99 shuffle must be stable.
POST_REBUILD_CORRECTIONS = {
    "image_008.jpg": {"num_birds": "1"},
    "image_056.jpg": {"num_birds": "3", "common_name": "Gray Heron / Asian Openbill"},
    "image_066.jpg": {"num_birds": "3", "common_name": "Grey Heron / Little Cormorant / Great Egret"},
    "image_077.jpg": {"num_birds": "1"},
    "image_078.jpg": {"num_birds": "1"},
    "image_082.jpg": {"num_birds": "3", "common_name": "Black-headed Ibis / Glossy Ibis / Wood Sandpiper"},
    "image_092.jpg": {"num_birds": "3"},
    "image_118.jpg": {"num_birds": "2"},
    "image_122.jpg": {"num_birds": "1"},
    "image_137.jpg": {"num_birds": "2"},
}

# ── Confusing species keywords per region ────────────────────────────────────
CONFUSING_KWS = {
    "US":        ["Gull", "Hummingbird", "Crane", "Grebe", "Green Heron",
                  "Night-Heron", "Scrub-Jay", "Scrub Jay", "Tern", "Loon"],
    "India":     ["Bee-eater", "Tern", "Cormorant", "Egret", "Flamingo"],
    "UK":        ["Gull", "Swan", "Tern"],
    "Singapore": ["Sunbird", "Myna", "Kingfisher", "Heron"],
}

CONFUSING_CATEGORIES = {
    "Gull": ["Gull"], "Tern": ["Tern"], "Hummingbird": ["Hummingbird"],
    "Grebe": ["Grebe"], "Heron": ["Heron"], "Scrub-Jay": ["Scrub-Jay", "Scrub Jay"],
    "Loon": ["Loon"], "Crane": ["Crane"], "Bee-eater": ["Bee-eater"],
    "Egret": ["Egret"], "Cormorant": ["Cormorant"], "Flamingo": ["Flamingo"],
    "Swan": ["Swan"], "Sunbird": ["Sunbird"], "Myna": ["Myna"],
    "Kingfisher": ["Kingfisher"], "Other": [],
}

LIKELY_CONFUSING = {
    "Western Gull": "California Gull, Herring Gull",
    "California Gull": "Western Gull, Herring Gull, Ring-billed Gull",
    "Bonaparte's Gull": "Heermann's Gull, Black-headed Gull",
    "Ring-billed Gull": "Common Gull, California Gull",
    "Glaucous-winged Gull": "Western Gull, Herring Gull",
    "Herring Gull": "Western Gull, California Gull, Glaucous-winged Gull",
    "Mew Gull": "Ring-billed Gull, Common Gull",
    "Laughing Gull": "Franklin's Gull",
    "Lesser Black-backed Gull": "Western Gull, Herring Gull",
    "Heermann's Gull": "Bonaparte's Gull",
    "Forster's Tern": "Common Tern",
    "Common Tern": "Forster's Tern, Arctic Tern",
    "Caspian Tern": "Royal Tern, Elegant Tern",
    "Royal Tern": "Caspian Tern, Elegant Tern",
    "Elegant Tern": "Royal Tern, Caspian Tern",
    "Arctic Tern": "Common Tern, Forster's Tern",
    "Least Tern": "Forster's Tern",
    "Anna's Hummingbird": "Costa's Hummingbird, Allen's Hummingbird",
    "Allen's Hummingbird": "Rufous Hummingbird, Anna's Hummingbird",
    "Rufous Hummingbird": "Allen's Hummingbird, Calliope Hummingbird",
    "Black-chinned Hummingbird": "Anna's Hummingbird, Costa's Hummingbird",
    "Calliope Hummingbird": "Rufous Hummingbird, Allen's Hummingbird",
    "Costa's Hummingbird": "Anna's Hummingbird, Black-chinned Hummingbird",
    "Western Grebe": "Clark's Grebe",
    "Clark's Grebe": "Western Grebe",
    "Pied-billed Grebe": "Horned Grebe, Eared Grebe",
    "Horned Grebe": "Eared Grebe, Pied-billed Grebe",
    "Eared Grebe": "Horned Grebe, Pied-billed Grebe",
    "Green Heron": "Black-crowned Night-Heron",
    "Black-crowned Night-Heron": "Green Heron",
    "California Scrub-Jay": "Island Scrub-Jay",
    "Island Scrub-Jay": "California Scrub-Jay",
    "Common Loon": "Pacific Loon",
    "Pacific Loon": "Common Loon, Red-throated Loon",
    "Red-throated Loon": "Pacific Loon",
    "Sandhill Crane": "Whooping Crane",
    "Whooping Crane": "Sandhill Crane",
    "Blue-tailed Bee-eater": "Asian Green Bee-eater, Blue-cheeked Bee-eater",
    "Asian Green Bee-eater": "Blue-tailed Bee-eater",
    "Green Bee-eater": "Blue-tailed Bee-eater",
    "Whiskered Tern": "Gull-billed Tern, White-winged Tern",
    "Gull-billed Tern": "Whiskered Tern",
    "Little Cormorant": "Indian Cormorant",
    "Indian Cormorant": "Little Cormorant",
    "Little Egret": "Great Egret, Intermediate Egret",
    "Great Egret": "Little Egret, Intermediate Egret",
    "Intermediate Egret": "Great Egret, Little Egret",
    "Eastern Cattle-Egret": "Little Egret",
    "Greater Flamingo": "Lesser Flamingo",
    "Lesser Flamingo": "Greater Flamingo",
    "Common Gull": "Ring-billed Gull, Mew Gull",
    "Black-headed Gull": "Common Gull, Bonaparte's Gull",
    "Mute Swan": "Whooper Swan, Bewick's Swan",
    "Whooper Swan": "Mute Swan, Bewick's Swan",
    "Crimson Sunbird": "Ornate Sunbird, Olive-backed Sunbird",
    "Ornate Sunbird": "Crimson Sunbird, Olive-backed Sunbird",
    "Olive-backed Sunbird": "Crimson Sunbird, Ornate Sunbird",
    "Javan Myna": "Common Myna, White-vented Myna",
    "Common Myna": "Javan Myna, White-vented Myna",
    "Collared Kingfisher": "White-throated Kingfisher, Common Kingfisher",
    "Grey Heron": "Purple Heron",
    "Gray Heron": "Purple Heron",
    "Purple Heron": "Grey Heron",
}


def strip_parens(name):
    return re.sub(r'\s*\(.*?\)\s*$', '', name).strip()

def parse_location(loc_str):
    try:
        parts = loc_str.strip().split(",")
        return float(parts[0].strip()), float(parts[1].strip())
    except Exception:
        return None, None

def confidence_bin(conf, threshold):
    r = 1.0 - threshold
    if conf < threshold + r * 0.33: return "low"
    elif conf < threshold + r * 0.67: return "mid"
    return "high"

def load_eligible(csv_path, threshold):
    rows = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                bc = int(row["bird_count"]); conf = float(row["top_confidence"])
                loc = row["location"].strip(); cl = row["current_label"].strip()
            except: continue
            if bc >= 1 and bc <= 3 and conf >= threshold and loc and loc != "No GPS Data" and cl:
                rows.append(row)
    return rows

def stratified_sample(eligible, threshold, quota, seed=42):
    rng = random.Random(seed)
    groups = defaultdict(list)
    for row in eligible:
        key = (row["current_label"], confidence_bin(float(row["top_confidence"]), threshold))
        groups[key].append(row)
    keys = sorted(groups.keys())
    for k in keys:
        rng.shuffle(groups[k])
        groups[k].sort(key=lambda r: float(r["top_confidence"]), reverse=True)
    pointers = {k: 0 for k in keys}
    selected = []
    while len(selected) < quota:
        added = False
        for k in keys:
            if pointers[k] < len(groups[k]):
                selected.append(groups[k][pointers[k]]); pointers[k] += 1; added = True
                if len(selected) >= quota: break
        if not added: break
    return selected

def get_category(label):
    for cat, kws in CONFUSING_CATEGORIES.items():
        if cat == "Other": continue
        if any(k.lower() in label.lower() for k in kws):
            return cat
    return "Other"

def get_confusing_label(label):
    parts = [p.strip() for p in label.split("/")]
    results = []
    for part in parts:
        c = LIKELY_CONFUSING.get(strip_parens(part), "")
        if c:
            results.append(c)
    return "; ".join(results) if results else ""


def main():
    # ── 1. Original 100-image selection (seed=42) ─────────────────────────────
    orig_100 = []
    for region, (fname, thresh) in REGION_CONFIG.items():
        elig = load_eligible(fname, thresh)
        quota = min(REGION_QUOTA[region], len(elig))
        sel = stratified_sample(elig, thresh, quota, seed=42)
        for r in sel:
            r["_region"] = region
        orig_100.extend(sel)
    print(f"Original selection: {len(orig_100)} images")

    # Build display_name → (region, row) lookup
    orig_map = {r["display_name"]: r for r in orig_100}

    # ── 2. Apply first-session corrections (by original image_001-100 number) ──
    corrected = []
    for i, row in enumerate(orig_100, 1):
        img_id = f"image_{i:03d}.jpg"
        if img_id in FIRST_SESSION_REMOVE:
            print(f"  Remove: {img_id} ({row['current_label']})")
            continue
        common_name = strip_parens(row["current_label"])
        num_birds   = row["bird_count"]
        if img_id in FIRST_SESSION_CORRECTIONS:
            c = FIRST_SESSION_CORRECTIONS[img_id]
            if "common_name" in c: common_name = c["common_name"]
            if "num_birds"   in c: num_birds   = c["num_birds"]
            print(f"  Fix {img_id}: {row['current_label']} → {common_name}, birds={num_birds}")
        corrected.append({
            "display_name": row["display_name"],
            "common_name":  common_name,
            "num_birds":    num_birds,
            "location":     row["location"],
        })
    print(f"After first-session corrections: {len(corrected)} images")
    already_selected = {r["display_name"] for r in corrected}
    # Also track the removed ones so we don't re-add them as confusing
    already_seen = {r["display_name"] for r in orig_100}

    # ── 3. Select 50 confusing images ─────────────────────────────────────────
    conf_candidates = []
    for region, (fname, thresh) in REGION_CONFIG.items():
        elig = load_eligible(fname, thresh)
        kws = CONFUSING_KWS.get(region, [])
        for row in elig:
            if row["display_name"] in already_seen: continue
            cl = row["current_label"]
            if any(k.lower() in cl.lower() for k in kws):
                row["_region"] = region
                row["_cat"]    = get_category(cl)
                conf_candidates.append(row)

    groups = defaultdict(list)
    for r in conf_candidates:
        groups[(r["_region"], r["_cat"])].append(r)
    for k in groups:
        groups[k].sort(key=lambda r: float(r["top_confidence"]))
    keys = sorted(groups.keys())
    pointers = {k: 0 for k in keys}
    conf_50 = []
    while len(conf_50) < 50:
        added = False
        for k in keys:
            if pointers[k] < len(groups[k]):
                conf_50.append(groups[k][pointers[k]]); pointers[k] += 1; added = True
                if len(conf_50) >= 50: break
        if not added: break

    from collections import Counter
    print(f"Confusing images selected: {len(conf_50)}")
    print("  By region:  ", dict(Counter(r["_region"] for r in conf_50)))
    print("  By category:", dict(Counter(r["_cat"]    for r in conf_50)))

    for row in conf_50:
        corrected.append({
            "display_name": row["display_name"],
            "common_name":  strip_parens(row["current_label"]),
            "num_birds":    row["bird_count"],
            "location":     row["location"],
        })

    # ── 4. Shuffle all 148 entries ────────────────────────────────────────────
    rng = random.Random(99)
    rng.shuffle(corrected)
    print(f"\nTotal to copy: {len(corrected)}")

    # ── 5. Load Photos library ────────────────────────────────────────────────
    print("Loading Photos library (Birds album)...")
    db = osxphotos.PhotosDB()
    birds_photos = [p for p in db.photos() if any("Birds" in a.title for a in p.album_info)]
    photo_map = {p.original_filename: p for p in birds_photos if p.original_filename}
    print(f"Birds album indexed: {len(photo_map)} photos")

    # ── 6. Clear images dir and re-copy ───────────────────────────────────────
    os.makedirs(IMAGES_DIR, exist_ok=True)
    for f in os.listdir(IMAGES_DIR):
        if f.endswith(".jpg"):
            os.remove(os.path.join(IMAGES_DIR, f))

    final_rows = []
    not_found  = []
    img_idx    = 1

    for entry in corrected:
        display_name = entry["display_name"]
        photo = photo_map.get(display_name)
        if photo is None:
            not_found.append(display_name); continue
        src = photo.path_edited if photo.path_edited else photo.path
        if src is None or not os.path.exists(str(src)):
            not_found.append(display_name); continue

        dest_name = f"image_{img_idx:03d}.jpg"
        shutil.copy2(str(src), os.path.join(IMAGES_DIR, dest_name))

        lat, lon = parse_location(entry["location"])
        final_rows.append({
            "image_id":                 dest_name,
            "num_birds":                entry["num_birds"],
            "common_name":              entry["common_name"],
            "latitude":                 round(lat) if lat is not None else "",
            "longitude":                round(lon) if lon is not None else "",
            "likely_confusing_species": get_confusing_label(entry["common_name"]),
        })
        img_idx += 1

    if not_found:
        print(f"Not found ({len(not_found)}): {not_found[:5]}")

    print(f"Images copied: {len(final_rows)}")

    # ── 7. Apply post-rebuild corrections ─────────────────────────────────────
    for row in final_rows:
        if row["image_id"] in POST_REBUILD_CORRECTIONS:
            c = POST_REBUILD_CORRECTIONS[row["image_id"]]
            if "num_birds"   in c: row["num_birds"]   = c["num_birds"]
            if "common_name" in c:
                row["common_name"] = c["common_name"]
                row["likely_confusing_species"] = get_confusing_label(c["common_name"])
            print(f"  Post-fix {row['image_id']}: {c}")

    # ── 9. Write labels.csv ───────────────────────────────────────────────────
    fieldnames = ["image_id", "num_birds", "common_name", "latitude", "longitude",
                  "likely_confusing_species"]
    with open(LABELS_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(final_rows)
    print(f"labels.csv written")

    # ── 10. Regenerate slideshow ──────────────────────────────────────────────
    data_js = json.dumps(final_rows, indent=2)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Bird Image Review</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #111; color: #eee; font-family: sans-serif; display: flex;
          flex-direction: column; align-items: center; justify-content: center;
          min-height: 100vh; padding: 16px; }}
  #frame {{ position: relative; width: 100%; max-width: 960px; }}
  #img {{ width: 100%; max-height: 68vh; object-fit: contain; display: block;
           background: #000; border-radius: 6px; }}
  #overlay {{ position: absolute; bottom: 0; left: 0; right: 0;
              background: rgba(0,0,0,.70); padding: 10px 14px;
              border-radius: 0 0 6px 6px; font-size: 14px; }}
  #label   {{ font-weight: 600; font-size: 17px; margin-bottom: 2px; }}
  #confuse {{ color: #f90; font-size: 13px; min-height: 18px; }}
  #rowmeta {{ display: flex; justify-content: space-between; margin-top: 4px;
              font-size: 12px; color: #aaa; }}
  #progress {{ width: 100%; height: 3px; background: #333; border-radius: 2px; margin: 8px 0 6px; }}
  #bar {{ height: 3px; background: #4af; border-radius: 2px; }}
  #controls {{ display: flex; gap: 10px; align-items: center; font-size: 13px; color: #999; }}
  button {{ background: #333; border: none; color: #eee; padding: 5px 14px;
            border-radius: 4px; cursor: pointer; font-size: 13px; }}
  button:hover {{ background: #555; }}
  #counter {{ min-width: 80px; text-align: center; }}
</style>
</head>
<body>
<div id="frame">
  <img id="img" src="" alt="">
  <div id="overlay">
    <div id="label"></div>
    <div id="confuse"></div>
    <div id="rowmeta">
      <span id="birds"></span>
      <span id="loc"></span>
    </div>
  </div>
</div>
<div id="progress"><div id="bar"></div></div>
<div id="controls">
  <button id="prevBtn">&#9664; Prev</button>
  <button id="pauseBtn">&#9646;&#9646; Pause</button>
  <button id="nextBtn">Next &#9654;</button>
  <span id="counter"></span>
  <label style="margin-left:10px">Speed:
    <select id="speed">
      <option value="500">0.5s</option>
      <option value="1000" selected>1s</option>
      <option value="2000">2s</option>
      <option value="3000">3s</option>
    </select>
  </label>
</div>
<script>
const data = {data_js};
let idx = 0, timer = null, paused = false, interval = 1000;
const img = document.getElementById('img');
const label = document.getElementById('label');
const confuse = document.getElementById('confuse');
const birds = document.getElementById('birds');
const loc = document.getElementById('loc');
const counter = document.getElementById('counter');
const bar = document.getElementById('bar');
const pauseBtn = document.getElementById('pauseBtn');
function show(i) {{
  const r = data[i];
  img.src = 'images/' + r.image_id;
  label.textContent = r.common_name;
  confuse.textContent = r.likely_confusing_species ? '⚠ Often confused with: ' + r.likely_confusing_species : '';
  birds.textContent = r.num_birds + (r.num_birds == 1 ? ' bird' : ' birds');
  loc.textContent = r.latitude + '°, ' + r.longitude + '°';
  counter.textContent = (i+1) + ' / ' + data.length;
  bar.style.width = ((i+1)/data.length*100) + '%';
}}
function next() {{ idx = (idx+1) % data.length; show(idx); }}
function prev() {{ idx = (idx-1+data.length) % data.length; show(idx); }}
function startTimer() {{ clearInterval(timer); timer = setInterval(next, interval); }}
pauseBtn.addEventListener('click', () => {{
  paused = !paused;
  pauseBtn.textContent = paused ? '▶ Resume' : '⏸ Pause';
  if (paused) clearInterval(timer); else startTimer();
}});
document.getElementById('prevBtn').addEventListener('click', () => {{ prev(); if (!paused) startTimer(); }});
document.getElementById('nextBtn').addEventListener('click', () => {{ next(); if (!paused) startTimer(); }});
document.getElementById('speed').addEventListener('change', e => {{ interval = +e.target.value; if (!paused) startTimer(); }});
document.addEventListener('keydown', e => {{
  if (e.key === ' ') {{ pauseBtn.click(); e.preventDefault(); }}
  if (e.key === 'ArrowRight') {{ next(); if (!paused) startTimer(); }}
  if (e.key === 'ArrowLeft') {{ prev(); if (!paused) startTimer(); }}
}});
show(0); startTimer();
</script>
</body>
</html>"""
    with open(SLIDESHOW, "w") as f:
        f.write(html)
    print(f"Slideshow regenerated: {SLIDESHOW}")


if __name__ == "__main__":
    main()