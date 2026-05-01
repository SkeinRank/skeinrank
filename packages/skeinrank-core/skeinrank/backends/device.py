from __future__ import annotations

from dataclasses import dataclass

from skeinrank.domain.errors import ContractError, ModelUnavailable


@dataclass(frozen=True)
class DeviceResolution:
    requested: str
    resolved: str
    fallback: bool
    reason: str | None = None


def resolve_device(
    *,
    requested: str,
    device_preference: list[str],
    cuda_available: bool,
    strict_cuda: bool,
) -> DeviceResolution:
    """Resolve a requested device into an actual device.

    Parameters
    ----------
    requested:
        "auto" | "cpu" | "cuda"
    device_preference:
        Ordered device preference list used when requested == "auto".
        Allowed values are "cuda" and "cpu".
    cuda_available:
        Whether CUDA execution is available in the current runtime.
    strict_cuda:
        If True and CUDA is requested, raise when CUDA is unavailable.

    Returns
    -------
    DeviceResolution
    """
    if requested not in {"auto", "cpu", "cuda"}:
        raise ContractError("device must be one of: auto, cpu, cuda")

    # Normalize/validate preference list.
    pref = device_preference or ["cuda", "cpu"]
    for d in pref:
        if d not in {"cuda", "cpu"}:
            raise ContractError("device_preference must contain only: cuda, cpu")

    if requested == "cpu":
        return DeviceResolution(
            requested="cpu", resolved="cpu", fallback=False, reason=None
        )

    if requested == "cuda":
        if cuda_available:
            return DeviceResolution(
                requested="cuda", resolved="cuda", fallback=False, reason=None
            )
        if strict_cuda:
            raise ModelUnavailable("Profile requires CUDA but CUDA is not available")
        return DeviceResolution(
            requested="cuda",
            resolved="cpu",
            fallback=True,
            reason="cuda requested but not available; falling back to cpu",
        )

    # requested == "auto"
    # Choose the first available in preference.
    for d in pref:
        if d == "cuda":
            if cuda_available:
                return DeviceResolution(
                    requested="auto", resolved="cuda", fallback=False, reason=None
                )
            continue
        if d == "cpu":
            # CPU is always available.
            # If CUDA was preferred first but unavailable, this counts as a fallback.
            fallback = len(pref) > 0 and pref[0] == "cuda"
            reason = "cuda preferred but not available; using cpu" if fallback else None
            return DeviceResolution(
                requested="auto", resolved="cpu", fallback=fallback, reason=reason
            )

    # Should never happen due to validation, but keep safe.
    return DeviceResolution(
        requested="auto", resolved="cpu", fallback=False, reason=None
    )
