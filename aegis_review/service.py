"""Task status contract and service boundary."""

from __future__ import annotations

from .domain import JobStatus


class InvalidStatusTransition(ValueError):
    """Raised when a job tries to skip or reverse its lifecycle."""


ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.CREATED: frozenset({JobStatus.QUEUED}),
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.FAILED}),
    JobStatus.RUNNING: frozenset({JobStatus.COMPLETED, JobStatus.FAILED}),
    JobStatus.COMPLETED: frozenset(),
    JobStatus.FAILED: frozenset({JobStatus.QUEUED}),
}


def validate_transition(current: JobStatus, target: JobStatus) -> None:
    """Validate the published job lifecycle before persistent state changes."""
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidStatusTransition(
            f"invalid job status transition: {current.value} -> {target.value}"
        )
