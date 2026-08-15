"""Background workers owned by the target-only application process."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from collections.abc import Callable

from core.task_registry import TaskRegistry
from infrastructure.queue.durable_work_wakeup import DurableWorkWakeups
from services.native.album_identification_service import AlbumIdentificationService
from services.native.identification_queue_service import IdentificationQueueService
from services.native.library_operation_supervisor import LibraryOperationSupervisor
from services.native.library_management_recovery_service import (
    LibraryManagementRecoveryService,
)
from services.native.background_workload_gate import BackgroundWorkloadGate
from services.native.library_contribution_verification_worker import (
    LibraryContributionVerificationWorker,
)

logger = logging.getLogger(__name__)
# Different bounded deadlines keep recovery passes from reopening four SQLite
# connections in the same event-loop tick after a quiet startup.
IDENTIFICATION_RECOVERY_INTERVAL_SECONDS = 31.0
OPERATION_RECOVERY_INTERVAL_SECONDS = 37.0
CONTRIBUTION_RECOVERY_INTERVAL_SECONDS = 43.0
ERROR_RETRY_INTERVAL_SECONDS = 1.0


def _worker_id(kind: str) -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{kind}"


def _log_worker_error(task: asyncio.Task[None], *, name: str) -> None:
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        logger.error(
            "%s stopped unexpectedly",
            name,
            exc_info=(type(error), error, error.__traceback__),
        )


async def run_target_identification_worker(
    queue_getter: Callable[[], IdentificationQueueService],
    service_getter: Callable[[], AlbumIdentificationService],
    *,
    worker_id: str | None = None,
    workload_gate: BackgroundWorkloadGate | None = None,
    work_wakeups: DurableWorkWakeups | None = None,
) -> None:
    owner = worker_id or _worker_id("identification")
    wakeups = work_wakeups or DurableWorkWakeups()
    while True:
        revision = wakeups.revision("identification")
        processed = False
        wait_seconds = IDENTIFICATION_RECOVERY_INTERVAL_SECONDS
        try:
            if workload_gate is None or not workload_gate.scan_active:
                queue = queue_getter()
                await queue.recover()
                if not await queue.is_paused():
                    job = None
                    if workload_gate is None or not workload_gate.scan_active:
                        job = await queue.claim(owner)
                    if job is not None:
                        await service_getter().run_claimed_job(job, owner)
                        processed = True
        except asyncio.CancelledError:
            break
        except Exception:  # noqa: BLE001 - a durable worker must survive one failed item
            logger.exception("Target identification worker iteration failed")
            wait_seconds = ERROR_RETRY_INTERVAL_SECONDS
        if processed:
            continue
        try:
            await wakeups.wait(
                "identification",
                after_revision=revision,
                timeout_seconds=wait_seconds,
            )
        except asyncio.CancelledError:
            break


async def run_target_operation_worker(
    supervisor_getter: Callable[[], LibraryOperationSupervisor],
    recovery_getter: Callable[[], LibraryManagementRecoveryService] | None = None,
    *,
    worker_id: str | None = None,
    work_wakeups: DurableWorkWakeups | None = None,
) -> None:
    owner = worker_id or _worker_id("operation")
    wakeups = work_wakeups or DurableWorkWakeups()
    while True:
        revision = wakeups.revision("operation")
        processed = False
        wait_seconds = OPERATION_RECOVERY_INTERVAL_SECONDS
        try:
            supervisor = supervisor_getter()
            await supervisor.recover()
            if recovery_getter is not None:
                await recovery_getter().recover_once()
            processed = await supervisor.run_once(owner) is not None
        except asyncio.CancelledError:
            break
        except Exception:  # noqa: BLE001 - a durable worker must survive one failed item
            logger.exception("Target operation worker iteration failed")
            wait_seconds = ERROR_RETRY_INTERVAL_SECONDS
        if processed:
            continue
        try:
            await wakeups.wait(
                "operation",
                after_revision=revision,
                timeout_seconds=wait_seconds,
            )
        except asyncio.CancelledError:
            break


async def run_library_contribution_verification_worker(
    worker_getter: Callable[[], LibraryContributionVerificationWorker],
    *,
    worker_id: str | None = None,
    work_wakeups: DurableWorkWakeups | None = None,
) -> None:
    owner = worker_id or _worker_id("library-contribution-verification")
    wakeups = work_wakeups or DurableWorkWakeups()
    while True:
        revision = wakeups.revision("contribution")
        processed = False
        wait_seconds = CONTRIBUTION_RECOVERY_INTERVAL_SECONDS
        try:
            worker = worker_getter()
            await worker.recover()
            processed = await worker.run_once(owner) is not None
        except asyncio.CancelledError:
            break
        except Exception:  # noqa: BLE001 - a durable worker must survive one failed item
            logger.exception(
                "Library contribution verification worker iteration failed"
            )
            wait_seconds = ERROR_RETRY_INTERVAL_SECONDS
        if processed:
            continue
        try:
            await wakeups.wait(
                "contribution",
                after_revision=revision,
                timeout_seconds=wait_seconds,
            )
        except asyncio.CancelledError:
            break


def start_target_identification_worker(
    queue_getter: Callable[[], IdentificationQueueService],
    service_getter: Callable[[], AlbumIdentificationService],
    work_wakeups: DurableWorkWakeups,
    workload_gate: BackgroundWorkloadGate | None = None,
) -> asyncio.Task[None]:
    name = "target-library-identification-worker"
    task = asyncio.create_task(
        run_target_identification_worker(
            queue_getter,
            service_getter,
            workload_gate=workload_gate,
            work_wakeups=work_wakeups,
        )
    )
    TaskRegistry.get_instance().register(name, task)
    task.add_done_callback(lambda item: _log_worker_error(item, name=name))
    return task


def start_target_operation_worker(
    supervisor_getter: Callable[[], LibraryOperationSupervisor],
    work_wakeups: DurableWorkWakeups,
    recovery_getter: Callable[[], LibraryManagementRecoveryService] | None = None,
) -> asyncio.Task[None]:
    name = "target-library-operation-worker"
    task = asyncio.create_task(
        run_target_operation_worker(
            supervisor_getter, recovery_getter, work_wakeups=work_wakeups
        )
    )
    TaskRegistry.get_instance().register(name, task)
    task.add_done_callback(lambda item: _log_worker_error(item, name=name))
    return task


def start_library_contribution_verification_worker(
    worker_getter: Callable[[], LibraryContributionVerificationWorker],
    work_wakeups: DurableWorkWakeups,
) -> asyncio.Task[None]:
    name = "library-contribution-verification-worker"
    task = asyncio.create_task(
        run_library_contribution_verification_worker(
            worker_getter, work_wakeups=work_wakeups
        )
    )
    TaskRegistry.get_instance().register(name, task)
    task.add_done_callback(lambda item: _log_worker_error(item, name=name))
    return task
