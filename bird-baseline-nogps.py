# %%
import kaggle_benchmarks as kbench
from dataclasses import dataclass
import re

@dataclass
class BirdID:
    bird_count: int
    common_name: str

def normalize_name(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r"\s*\(.*?\)", " ", name)
    name = re.sub(r"[-_']", " ", name)
    return re.sub(r"\s+", " ", name).strip()

SYNONYM_GROUPS = [
    {"gray heron", "grey heron"},
    {"gray plover", "grey plover", "black bellied plover"},
    {"common hill myna", "hill myna"},
    {"eurasian kestrel", "common kestrel"},
    {"asian green bee eater", "green bee eater"},
    {"eurasian blue tit", "blue tit"},
    {"black crowned night heron", "black crowned night heron juvenile"},
    {"cattle egret", "eastern cattle egret"},
    {"asian openbill", "asian openbill stork"},
]

def canonical(name: str) -> str:
    norm = normalize_name(name)
    for group in SYNONYM_GROUPS:
        if norm in group:
            return min(group)
    return norm

def _split_species(text: str) -> set:
    parts = re.split(r"[/,;&]|\band\b", text)
    return {canonical(p) for p in parts if p.strip()}

def species_match(predicted: str, ground_truth: str) -> bool:
    pred_set = _split_species(predicted)
    truth_set = _split_species(ground_truth)
    if len(truth_set) == 1:
        return bool(pred_set & truth_set)
    return pred_set == truth_set

def _send_image(image_path: str):
    import base64, io
    from PIL import Image
    img = Image.open(image_path).convert("RGB")
    img.thumbnail((1024, 1024))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    kbench.user.send(kbench.content_types.images.from_base64(b64))

def _prompt_with_retry(llm, prompt_text):
    import time, random
    for attempt in range(6):
        try:
            return llm.prompt(prompt_text, schema=BirdID)
        except Exception as e:
            if "429" in str(e) and attempt < 5:
                time.sleep((2 ** attempt) + random.random())
            else:
                raise

def _location_hint(latitude: float, longitude: float) -> str:
    return f" The photo was taken at approximately {latitude}°, {longitude}°." if latitude and longitude else ""

@kbench.task(name="bird-id-baseline-nogps")
def bird_id_baseline(llm, image_path: str, num_birds: int, common_name: str,
                     latitude: float = 0.0, longitude: float = 0.0) -> bool:
    """Baseline species identification with GPS location hint.
    Score: True = species correct, False = wrong."""
    _send_image(image_path)
    result = _prompt_with_retry(
        llm,
        "How many birds are in the image, and what is the common name of the species shown?"
        # NO-GPS ABLATION: location hint deliberately omitted
        + " If multiple species are present, list them separated by ' / '.",
    )
    species_correct = species_match(result.common_name, common_name)
    kbench.assertions.assert_true(species_correct, expectation="Species correctly identified")
    return species_correct

# %%
import pandas as pd, os

DATA_DIR = "/kaggle/input/datasets/jupiter79/bird-benchmark"

df = pd.read_csv(os.path.join(DATA_DIR, "labels.csv"))
df["image_path"] = df["image_id"].apply(lambda x: os.path.join(DATA_DIR, "images", x))
df["latitude"]  = df["latitude"].fillna(0.0)
df["longitude"] = df["longitude"].fillna(0.0)

bird_eval = df[["image_path", "num_birds", "common_name", "latitude", "longitude"]]

MAX_ROWS = None

# %%
# ── Task: Baseline identification ────────────────────────────────────────────
# Run via: kaggle b t run bird-id-baseline-nogps -m <model> --wait
print("=== Baseline (NO-GPS): species identification NO location hint (ablation) ===")

eval_data = bird_eval
if MAX_ROWS is not None:
    eval_data = eval_data.head(MAX_ROWS)
n = len(eval_data)

runs = bird_id_baseline.evaluate(
    stop_condition=lambda runs, _n=n: len(runs) == _n,
    llm=[kbench.llm],
    evaluation_data=eval_data,
    n_jobs=1,
    on_failure="continue",
)
results = [row["result"] for _, row in runs.as_dataframe().iterrows()]
n_err = len(runs.errored_runs) if hasattr(runs, "errored_runs") else 0

correct = sum(1 for r in results if r is True)
print(f"  Species correct: {correct}/{len(results)} = {correct/len(results):.1%}")
if n_err:
    print(f"  Errored: {n_err} row(s)")
