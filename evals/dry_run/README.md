# Dry-run outputs: FAKE model, NOT results

Everything in this folder was produced with `--dry-run`, which uses `FakeLLM` (keyword rules + templates)
instead of a language model. It only proves that the evaluation pipeline runs end to end.
Never quote these numbers. Real runs are written to `evals/results/`.
