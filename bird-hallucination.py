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

def _is_empty_response(name: str) -> bool:
    if not name:
        return True
    return normalize_name(name) in {"none", "no bird", "no birds", "n a", "na", "unknown", "not applicable"}

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

@kbench.task(name="bird-id-hallucination")
def bird_id_hallucination(llm, image_path: str) -> bool:
    """Unprompted hallucination: does the model correctly abstain on a non-bird image?
    Score: True = correctly abstained, False = hallucinated a bird."""
    _send_image(image_path)
    result = _prompt_with_retry(
        llm,
        "How many birds are in the image, and what is the common name of the species shown?"
        " If there are no birds, set bird_count to 0 and common_name to 'none'."
        " If multiple species are present, list them separated by ' / '.",
    )
    abstained = not (result.bird_count > 0 or not _is_empty_response(result.common_name))
    kbench.assertions.assert_true(abstained, expectation="Correctly abstained on non-bird image")
    return abstained

# %%
import pandas as pd, os

DATA_DIR    = "/kaggle/input/datasets/jupiter79/bird-benchmark"
HABITAT_DIR = os.path.join(DATA_DIR, "habitat_images")

habitat_meta = pd.read_csv(os.path.join(HABITAT_DIR, "habitat_metadata.csv"))
habitat_meta["image_path"] = habitat_meta["filename"].apply(
    lambda x: os.path.join(HABITAT_DIR, x)
)

decoy_eval = habitat_meta[["image_path"]]

MAX_ROWS = None

# %%
# ── Task: Hallucination ───────────────────────────────────────────────────────
# Run via: kaggle b t run bird-id-hallucination -m <model> --wait
print("=== Hallucination: does the model abstain on non-bird images? ===")

eval_data = decoy_eval
if MAX_ROWS is not None:
    eval_data = eval_data.head(MAX_ROWS)
n = len(eval_data)

runs = bird_id_hallucination.evaluate(
    stop_condition=lambda runs, _n=n: len(runs) == _n,
    llm=[kbench.llm],
    evaluation_data=eval_data,
    n_jobs=1,
    on_failure="continue",
)
results = [row["result"] for _, row in runs.as_dataframe().iterrows()]
n_err = len(runs.errored_runs) if hasattr(runs, "errored_runs") else 0

abstained = sum(1 for r in results if r is True)
hallucinated = sum(1 for r in results if r is False)
print(f"  Abstained (correct): {abstained}/{len(results)} = {abstained/len(results):.1%}")
print(f"  Hallucinated:        {hallucinated}/{len(results)} = {hallucinated/len(results):.1%}")
if n_err:
    print(f"  Errored: {n_err} row(s)")
