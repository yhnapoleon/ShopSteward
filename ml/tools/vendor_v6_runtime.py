"""Extract unchanged inference kernels from a read-only research checkout.

Used when updating vendored runtime, never at serving time. Review generated
changes together with numerical parity tests before accepting a new version.
"""

import argparse
import ast
from pathlib import Path


def extract(path, names):
    text = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(text)
    parts = []
    for node in tree.body:
        ids = {node.name} if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else set()
        if isinstance(node, ast.Assign):
            ids = {t.id for t in node.targets if isinstance(t, ast.Name)}
        if ids & set(names):
            parts.append(ast.get_source_segment(text, node))
    return "\n\n\n".join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("research_root", type=Path)
    args = parser.parse_args()
    source = args.research_root / "ml/src/shopsteward_ml"
    out = Path(__file__).resolve().parents[1] / "src/shopsteward_ml"
    header = '"""Vendored unchanged inference kernels from ShopSteward-forecast; no training imports."""\nfrom __future__ import annotations\n'
    constants = extract(
        source / "features.py",
        [
            "ID_CATEGORY_FIELDS",
            "EVENT_CATEGORY_FIELDS",
            "CATEGORY_FIELDS",
            "OFFSET_DAYS",
            "ROLLING_WINDOWS",
            "HISTORY_FEATURE_COLUMNS",
            "CALENDAR_FEATURE_COLUMNS",
            "CATEGORY_FEATURE_COLUMNS",
            "FEATURE_COLUMNS",
        ],
    )
    constants += "\n\n" + extract(
        source / "specialization/features.py",
        [
            "ALIGNED_FEATURE_COLUMNS",
            "STATE_FEATURE_COLUMNS",
            "PRICE_FEATURE_COLUMNS",
            "_BLOCK_COLUMNS",
            "_CONFIG_BLOCKS",
            "EXTRA_FEATURE_COLUMNS",
        ],
    )
    out.joinpath("_constants.py").write_text(header + constants + "\n", encoding="utf-8")
    kernels = extract(source / "specialization/data_kernels.py", ["_windows", "_state"])
    out.joinpath("_state.py").write_text(
        header + "import numpy as np\n\n" + kernels + "\n", encoding="utf-8"
    )
    data = extract(
        source / "demo_v5/data.py",
        [
            "METADATA",
            "NN_CATEGORIES",
            "DAILY_COLUMNS",
            "DISABLED_CALENDAR_COLUMNS",
            "_history_features",
            "build_examples",
        ],
    )
    imports = "import numpy as np\nimport pandas as pd\nfrom ._constants import (CATEGORY_FIELDS, FEATURE_COLUMNS, HISTORY_FEATURE_COLUMNS, ID_CATEGORY_FIELDS, OFFSET_DAYS, ROLLING_WINDOWS, ALIGNED_FEATURE_COLUMNS, EXTRA_FEATURE_COLUMNS, STATE_FEATURE_COLUMNS)\nfrom ._state import _windows, _state\n\n"
    out.joinpath("_features_v5.py").write_text(header + imports + data + "\n", encoding="utf-8")
    data = extract(source / "demo_v6/features.py", ["EXTRA_COLUMNS", "enrich"])
    out.joinpath("_features_v6.py").write_text(
        header + "import numpy as np\nimport pandas as pd\n\n" + data + "\n", encoding="utf-8"
    )
    neural = extract(
        source / "demo_v5/neural.py",
        ["NeuralForecast", "_validate_examples", "_batch", "predict_neural", "load_neural"],
    )
    out.joinpath("_neural.py").write_text(
        header
        + "from pathlib import Path\nimport numpy as np\nimport torch\nfrom torch import nn\n\n"
        + neural
        + "\n",
        encoding="utf-8",
    )
    trees = extract(
        source / "demo_v6/models.py", ["POOLED", "_groups", "_scale", "_restore", "predict", "load"]
    )
    out.joinpath("_trees_v6.py").write_text(
        header
        + "import json\nfrom pathlib import Path\nimport numpy as np\nimport lightgbm as lgb\n\n"
        + trees
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
