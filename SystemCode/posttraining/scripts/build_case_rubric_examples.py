"""Build a new synthetic rubric bundle; never modify historical results."""

import argparse
from pathlib import Path

from shopsteward_pt.case_eval.examples import build_examples

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output-dir", type=Path, required=True)
args = parser.parse_args()
build_examples(args.output_dir)
print(f"Synthetic examples created at {args.output_dir.resolve()}; no model was called.")
