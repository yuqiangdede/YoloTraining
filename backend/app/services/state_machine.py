from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSING = "PAUSING"
    PAUSED = "PAUSED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class InvalidTransition(ValueError):
    pass


ALLOWED_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.CANCELLED},
    JobStatus.RUNNING: {JobStatus.PAUSING, JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.PAUSING: {JobStatus.PAUSED, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.PAUSED: {JobStatus.QUEUED, JobStatus.CANCELLED},
    JobStatus.SUCCEEDED: set(),
    JobStatus.FAILED: {JobStatus.QUEUED},
    JobStatus.CANCELLED: set(),
}


def transition(current: JobStatus, target: JobStatus) -> JobStatus:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransition(f"任务不能从 {current} 切换到 {target}")
    return target
