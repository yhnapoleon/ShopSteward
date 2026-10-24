"""Vendored unchanged inference kernels from ShopSteward-forecast; no training imports."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from torch import nn


class NeuralForecast(nn.Module):
    """Shared MLP with historical scaling and four static embeddings."""

    def __init__(self, cat_sizes: list[int], batch_size: int = 512, threads: int = 4):
        super().__init__()
        if len(cat_sizes) != 4 or any(size < 1 for size in cat_sizes):
            raise ValueError("cat_sizes must contain four positive sizes including UNKNOWN")
        self.cat_sizes = [int(size) for size in cat_sizes]
        self.batch_size = int(batch_size)
        self.threads = int(threads)
        self.embeddings = nn.ModuleList([nn.Embedding(size, 4) for size in self.cat_sizes])
        self.network = nn.Sequential(
            nn.Linear(84 + 28 + 1 + 4 * 4, 128),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(64, 7),
            nn.Softplus(),
        )

    def forward(self, history, calendar, categories, scale):
        embedded = []
        for column, embedding in enumerate(self.embeddings):
            category = categories[:, column]
            category = torch.where(
                (category >= 0) & (category < self.cat_sizes[column]), category, 0
            )
            embedded.append(embedding(category))
        features = torch.cat([history, calendar, torch.log1p(scale).unsqueeze(1), *embedded], dim=1)
        return self.network(features) * scale.unsqueeze(1)


def _validate_examples(examples: dict, *, targets: bool = False) -> int:
    count = len(examples["scale"])
    dimensions = {
        "nn_history": (count, 84),
        "nn_calendar": (count, 28),
        "nn_categories": (count, 4),
        "scale": (count,),
    }
    if targets:
        dimensions["y"] = (count, 7)
    for name, shape in dimensions.items():
        array = np.asarray(examples[name])
        if array.shape != shape or not np.isfinite(array).all():
            raise ValueError(f"Invalid {name}: expected finite array of shape {shape}")
    if np.any(examples["scale"] < 1):
        raise ValueError("scale must be max(mean28, 1)")
    if targets and np.any(examples["y"] < 0):
        raise ValueError("Training labels must be nonnegative")
    return count


def _batch(examples: dict, index):
    # Slice or gather only this batch; full training arrays stay in NumPy storage.
    return (
        torch.as_tensor(examples["nn_history"][index], dtype=torch.float32),
        torch.as_tensor(examples["nn_calendar"][index], dtype=torch.float32),
        torch.as_tensor(examples["nn_categories"][index], dtype=torch.int64),
        torch.as_tensor(examples["scale"][index], dtype=torch.float32),
    )


def predict_neural(model: NeuralForecast, examples: dict) -> np.ndarray:
    """Return original-unit daily point forecasts in input order, in small batches."""
    count = _validate_examples(examples)
    result = np.empty((count, 7), dtype=np.float32)
    model.eval()
    with torch.inference_mode():
        for start in range(0, count, model.batch_size):
            index = slice(start, start + model.batch_size)
            result[index] = model(*_batch(examples, index)).cpu().numpy()
    if not np.isfinite(result).all() or np.any(result < 0):
        raise FloatingPointError("Neural predictions must be finite and nonnegative")
    return result


def load_neural(path: Path) -> NeuralForecast:
    """Load a locally produced v5 artifact using Torch's restricted weights loader."""
    payload = torch.load(Path(path), map_location="cpu", weights_only=True)
    if payload["format_version"] != 1:
        raise ValueError("Unsupported neural artifact version")
    model = NeuralForecast(payload["cat_sizes"], payload["batch_size"], payload["threads"])
    torch.set_num_threads(model.threads)
    model.load_state_dict(payload["state_dict"], strict=True)
    model.eval()
    return model
