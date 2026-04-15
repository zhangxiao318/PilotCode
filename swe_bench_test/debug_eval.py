import sys
sys.stdout.reconfigure(line_buffering=True)

print("[DEBUG] Importing...", flush=True)
from swebench.harness.run_evaluation import main
from swebench.harness.utils import load_swebench_dataset, get_predictions_from_file
from swebench.harness.constants import KEY_INSTANCE_ID, MAP_REPO_VERSION_TO_SPECS

# Patch pytest spec to use Python 3.10 (current pytest main requires >=3.10)
if 'pytest-dev/pytest' in MAP_REPO_VERSION_TO_SPECS:
    for ver in MAP_REPO_VERSION_TO_SPECS['pytest-dev/pytest']:
        MAP_REPO_VERSION_TO_SPECS['pytest-dev/pytest'][ver]['python'] = '3.10'

print("[DEBUG] Loading dataset...", flush=True)
dataset = load_swebench_dataset('/tmp/mini_dataset_pytest.json', 'test')
print(f"[DEBUG] Dataset loaded: {len(dataset)} instances", flush=True)

print("[DEBUG] Loading predictions...", flush=True)
predictions = get_predictions_from_file('/tmp/predictions_gold.jsonl', '/tmp/mini_dataset_pytest.json', 'test')
print(f"[DEBUG] Predictions loaded: {len(predictions)}", flush=True)

pred_map = {pred[KEY_INSTANCE_ID]: pred for pred in predictions}
print(f"[DEBUG] Prediction map: {list(pred_map.keys())}", flush=True)

print("[DEBUG] Calling main()...", flush=True)
main(
    dataset_name='/tmp/mini_dataset_pytest.json',
    split='test',
    instance_ids=[],
    predictions_path='/tmp/predictions_gold.jsonl',
    max_workers=1,
    force_rebuild=True,
    cache_level='env',
    clean=False,
    open_file_limit=4096,
    run_id='pilotcode_pytest',
    timeout=1800,
    namespace=None,
    rewrite_reports=False,
    modal=False,
)
print("[DEBUG] Done", flush=True)
