"""Filename suffixes for trackline processing runs."""


def suffix_for_run(run_label: str) -> str:
    return "" if run_label == "full" else f"_{run_label}"
