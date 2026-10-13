import sys
from pathlib import Path

# the plugin is a package under plugins/: `import psyche`
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
