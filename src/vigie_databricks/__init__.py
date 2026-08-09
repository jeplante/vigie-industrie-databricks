"""Slice 1 Bronze package for the Databricks Vigie project."""

__all__ = ["__version__", "BronzeLoadResult", "load_bronze_observations"]

__version__ = "0.2.0"


def __getattr__(name: str):
	if name in {"BronzeLoadResult", "load_bronze_observations"}:
		from .bronze import BronzeLoadResult, load_bronze_observations

		symbols = {
			"BronzeLoadResult": BronzeLoadResult,
			"load_bronze_observations": load_bronze_observations,
		}
		return symbols[name]
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
