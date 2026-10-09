| Strategy | Text | Model | Runs | Success | Mean score | Coverage | Contradiction runs | Failed-subtask runs | Model calls | Tool calls | Input tok | Output tok | Median ms | MAST |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R0 fixed | seed | deepseek-flash | 12 | 12/12 | 1.0 | 1.0 | 0 | 0 | 1 | 0 | 4434 | 6394 | 25320 | — |
| R1 single | seed | deepseek-flash | 12 | 11/12 | 0.972 | 0.972 | 0 | 0 | 2 | 4 | 13433 | 5167 | 18515 | — |
| R2 static_multi | seed | deepseek-flash | 12 | 10/12 | 0.806 | 0.972 | 0 | 1 | 6.17 | 6.25 | 34747 | 12112 | 26218 | FM-1.1×1, FM-1.3×2, FM-3.2×2 |
| R3 adaptive_multi | seed | deepseek-flash | 12 | 8/12 | 0.583 | 1.0 | 0 | 1 | 7.92 | 7.17 | 43196 | 13476 | 34303 | FM-1.1×1, FM-1.3×3, FM-3.2×2 |
