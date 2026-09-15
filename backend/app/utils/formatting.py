"""Human-readable formatting helpers shared by the API and the CLI."""
from __future__ import annotations


def format_duration(seconds: float | None) -> str:
    """604834 -> '6d 23h 0m'. Keeps at most two non-zero units for readability."""
    if seconds is None:
        return "N/A"
    seconds = int(round(seconds))
    if seconds < 0:
        return "N/A"
    if seconds < 60:
        return f"{seconds}s"

    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    units: list[str] = []
    if days:
        units.append(f"{days}d")
    if hours:
        units.append(f"{hours}h")
    if minutes and days == 0:
        units.append(f"{minutes}m")
    if not units:
        units.append(f"{secs}s")

    return " ".join(units[:2])


def confidence_label(sample_size: int) -> str:
    """Coarse, sample-size-only confidence label. Never a claim of statistical rigor."""
    if sample_size < 5:
        return "Very low"
    if sample_size < 10:
        return "Low"
    if sample_size < 30:
        return "Moderate"
    if sample_size < 100:
        return "High"
    return "Very high"
