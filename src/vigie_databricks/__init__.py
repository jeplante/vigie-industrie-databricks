"""Slice 2 Bronze+Silver package for the Databricks Vigie project."""

__all__ = [
	"__version__",
	"BronzeLoadResult",
	"load_bronze_observations",
	"SilverLoadResult",
	"load_silver_observations",
	"classify_rejection_reason",
]

__version__ = "0.2.0"


def __getattr__(name: str):
	if name in {"BronzeLoadResult", "load_bronze_observations"}:
		from .bronze import BronzeLoadResult, load_bronze_observations

		symbols = {
			"BronzeLoadResult": BronzeLoadResult,
			"load_bronze_observations": load_bronze_observations,
		}
		return symbols[name]
	if name in {"SilverLoadResult", "load_silver_observations", "classify_rejection_reason"}:
		from .silver import (
			SilverLoadResult,
			classify_rejection_reason,
			load_silver_observations,
		)

		symbols = {
			"SilverLoadResult": SilverLoadResult,
			"load_silver_observations": load_silver_observations,
			"classify_rejection_reason": classify_rejection_reason,
		}
		return symbols[name]
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
