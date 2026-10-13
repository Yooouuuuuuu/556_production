# plugins/ — our Python that plugs INTO Hermes

Hermes extension points are Python by contract (memory providers, platform adapters, skills).
Source lives here; Hermes loads user plugins from `home/plugins/<name>/`, so `setup-vendor.ps1`
links each plugin directory there (directory junction) and `vendor/hermes-agent` stays pristine.

- `kokoro/` — the memory provider on **KeepsakeDB** (`D:\dev\KeepsakeDB`, installed into the
  Hermes venv with `uv pip install -e`). Activated by `memory.provider: kokoro` in
  `home/config.yaml`; configured by `home/kokoro.json` (db path per profile, embedder, L2 LLM,
  memory language, thresholds, backup dir, log). Store: `home/memory/<profile>.db`;
  snapshots: `home/backups/`; operational log: `home/logs/keepsake.jsonl`.
  Inspect from the terminal: `D:\dev\KeepsakeDB\.venv\Scripts\keepsake --db home\memory\default.db stats`.
