| Strategy | Text | Model | Runs | Success | Mean score | Coverage | Contradiction runs | Failed-subtask runs | Model calls | Tool calls | Input tok | Output tok | Median ms | MAST |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R0 fixed | gepa-r1 | deepseek-flash | 24 | 24/24 | 1.0 | 1.0 | 0 | 0 | 1 | 0 | 4670 | 5915 | 21787 | — |
| R0 fixed | seed | deepseek-flash | 24 | 23/24 | 0.986 | 0.986 | 0 | 0 | 1 | 0 | 4546 | 6376 | 22211 | FM-3.2×1 |
| R1 single | gepa-r1 | deepseek-flash | 24 | 24/24 | 1.0 | 1.0 | 0 | 0 | 2 | 4 | 14062 | 5071 | 18140 | — |
| R1 single | seed | deepseek-flash | 24 | 21/24 | 0.875 | 0.875 | 0 | 2 | 2 | 4.04 | 13754 | 4817 | 17749 | FM-1.1×1, FM-3.2×1 |
| R2 static_multi | gepa-r1 | deepseek-flash | 24 | 22/24 | 0.889 | 0.972 | 0 | 2 | 6 | 5.96 | 36257 | 13245 | 27562 | FM-1.1×1, FM-1.3×3, FM-3.2×4 |
| R2 static_multi | seed | deepseek-flash | 24 | 21/24 | 0.833 | 1.0 | 0 | 1 | 6.33 | 6.46 | 36772 | 12669 | 27344 | FM-1.3×6, FM-3.2×3 |
| R3 adaptive_multi | gepa-r1 | deepseek-flash | 24 | 22/24 | 0.875 | 1.0 | 0 | 1 | 7 | 6.71 | 42957 | 14182 | 35257 | FM-1.1×1, FM-1.3×4 |
| R3 adaptive_multi | seed | deepseek-flash | 24 | 18/24 | 0.708 | 1.0 | 0 | 1 | 7.83 | 6.83 | 44372 | 14271 | 34117 | FM-1.1×1, FM-1.3×8, FM-3.2×3 |
