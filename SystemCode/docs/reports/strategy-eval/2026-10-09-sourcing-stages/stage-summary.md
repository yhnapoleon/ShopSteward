| Stage | Models | Text | Partition | Passed | Mean score | First reading | Failures | Model calls | Median ms |
|---|---|---|---|---|---|---|---|---|---|
| explain | gpt-6-luna | seed | evo-val | 26/36 | 0.833 | — | AGENT_MODEL_INCOMPLETE x1, candidate-unstated x1, contradiction x1, gap-unstated x6, unsupported_claim x2 | 1 | 22069 |
| read | deepseek-flash | seed | evo-val | 32/33 | 0.97 | 30/33 | minimum_order_quantity x1, unit_price_minor x1 | 2.21 | 6406 |
| read | deepseek-flash | seed | smoke | 42/42 | 1.0 | 39/42 | — | 2.14 | 6937 |
