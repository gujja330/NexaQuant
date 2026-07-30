"""Evidence Cycle · Phases 1-3 of operator's post-lock roadmap.

'Up to now, you've been building features. Going forward, you should
build evidence.' — operator

These modules do NOT add new engines, new models, or new Telegram
sections. They compute proof-of-behavior from the existing
`reports/learning.parquet` closed-trade corpus and emit measurable
outputs that feed back into existing displays.

  calibration                — confidence-bucket → observed win rate
  alpha_validation           — expected alpha vs realized return
  yoy_improvement            — year-over-year win rate + median return
  model_attribution_longitudinal — per-model IC over rolling windows

All outputs land at `reports/evidence/*.json`. Article 101.2 · pure
measurement · zero prediction · zero architecture change.
"""
from .calibration import compute_calibration, run_calibration, SCHEMA_FINGERPRINT as CAL_FP
from .alpha_validation import compute_alpha_validation, run_alpha_validation, SCHEMA_FINGERPRINT as AV_FP
from .yoy_improvement import compute_yoy_report, run_yoy, SCHEMA_FINGERPRINT as YOY_FP
from .model_attribution_longitudinal import compute_rolling_ic, run_rolling_ic, SCHEMA_FINGERPRINT as RIC_FP

__all__ = [
    "compute_calibration", "run_calibration", "CAL_FP",
    "compute_alpha_validation", "run_alpha_validation", "AV_FP",
    "compute_yoy_report", "run_yoy", "YOY_FP",
    "compute_rolling_ic", "run_rolling_ic", "RIC_FP",
]
