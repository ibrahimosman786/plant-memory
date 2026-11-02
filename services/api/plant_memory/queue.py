"""Job queue with at-least-once semantics and idempotency keys.

Both backends deliver the same message shape:
  {"job": "<stage>", "idempotency_key": "...", "payload": {...}}
Consumers must be idempotent (see ingestion.pipeline.ProcessedJob ledger). Standard SQS can
deliver a message more than once; the Postgres backend deliberately mirrors that behaviour.
"""

from __future__ import annotations

import json
import socket
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text, update

from .config import get_settings
from .db.models import JobQueue
from .db.session import scoped_session

INGEST_QUEUE = "ingest"


@dataclass
class Message:
    id: str
    job: str
    idempotency_key: str
    payload: dict
    attempts: int
    receipt: str


class Queue(ABC):
    @abstractmethod
    def enqueue(self, job: str, idempotency_key: str, payload: dict, delay_seconds: int = 0) -> bool: ...

    @abstractmethod
    def receive(self, max_messages: int = 1, visibility_seconds: int = 300) -> list[Message]: ...

    @abstractmethod
    def ack(self, message: Message) -> None: ...

    @abstractmethod
    def nack(self, message: Message, error: str, retry_delay_seconds: int = 30) -> None: ...


class PostgresQueue(Queue):
    """SELECT ... FOR UPDATE SKIP LOCKED queue. Dead-letters after max_attempts."""

    def __init__(self, queue: str = INGEST_QUEUE):
        self.queue = queue
        self.worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"

    def enqueue(self, job: str, idempotency_key: str, payload: dict, delay_seconds: int = 0) -> bool:
        with scoped_session(None) as s:
            exists = s.execute(select(JobQueue.id).where(JobQueue.idempotency_key == idempotency_key)).first()
            if exists:
                return False
            s.add(JobQueue(queue=self.queue, payload={"job": job, "payload": payload}, idempotency_key=idempotency_key,
                           available_at=datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)))
            return True

    def receive(self, max_messages: int = 1, visibility_seconds: int = 300) -> list[Message]:
        now = datetime.now(timezone.utc)
        out: list[Message] = []
        with scoped_session(None) as s:
            # Reclaim expired in-flight messages (visibility timeout), as SQS would.
            s.execute(update(JobQueue).where(JobQueue.queue == self.queue, JobQueue.status == "in_flight",
                                             JobQueue.locked_at < now - timedelta(seconds=visibility_seconds))
                      .values(status="queued", locked_at=None, locked_by=None))
            rows = s.execute(
                text("""SELECT id FROM job_queue WHERE queue = :q AND status = 'queued' AND available_at <= :now
                        ORDER BY available_at LIMIT :n FOR UPDATE SKIP LOCKED"""),
                {"q": self.queue, "now": now, "n": max_messages},
            ).fetchall()
            for (jid,) in rows:
                job = s.get(JobQueue, jid)
                job.status = "in_flight"
                job.locked_at = now
                job.locked_by = self.worker_id
                job.attempts += 1
                out.append(Message(str(job.id), job.payload["job"], job.idempotency_key, job.payload["payload"], job.attempts, str(job.id)))
        return out

    def ack(self, message: Message) -> None:
        with scoped_session(None) as s:
            s.execute(update(JobQueue).where(JobQueue.id == uuid.UUID(message.id)).values(status="done"))

    def nack(self, message: Message, error: str, retry_delay_seconds: int = 30) -> None:
        with scoped_session(None) as s:
            job = s.get(JobQueue, uuid.UUID(message.id))
            if job is None:
                return
            job.last_error = error[:4000]
            if job.attempts >= job.max_attempts:
                job.status = "dead"  # dead-letter
            else:
                job.status = "queued"
                job.available_at = datetime.now(timezone.utc) + timedelta(seconds=retry_delay_seconds * job.attempts)
            job.locked_at = None
            job.locked_by = None


class SqsQueue(Queue):
    def __init__(self, queue_url: str, region: str):
        import boto3

        self.client = boto3.client("sqs", region_name=region)
        self.url = queue_url

    def enqueue(self, job: str, idempotency_key: str, payload: dict, delay_seconds: int = 0) -> bool:
        body = json.dumps({"job": job, "idempotency_key": idempotency_key, "payload": payload})
        self.client.send_message(QueueUrl=self.url, MessageBody=body, DelaySeconds=min(delay_seconds, 900))
        return True  # dedupe happens in the consumer ledger for standard queues

    def receive(self, max_messages: int = 1, visibility_seconds: int = 300) -> list[Message]:
        resp = self.client.receive_message(QueueUrl=self.url, MaxNumberOfMessages=max_messages, VisibilityTimeout=visibility_seconds,
                                           WaitTimeSeconds=10, AttributeNames=["ApproximateReceiveCount"])
        out = []
        for m in resp.get("Messages", []):
            body = json.loads(m["Body"])
            out.append(Message(m["MessageId"], body["job"], body["idempotency_key"], body["payload"],
                               int(m.get("Attributes", {}).get("ApproximateReceiveCount", "1")), m["ReceiptHandle"]))
        return out

    def ack(self, message: Message) -> None:
        self.client.delete_message(QueueUrl=self.url, ReceiptHandle=message.receipt)

    def nack(self, message: Message, error: str, retry_delay_seconds: int = 30) -> None:
        # Let visibility expire; SQS redrive policy moves it to the DLQ after maxReceiveCount.
        self.client.change_message_visibility(QueueUrl=self.url, ReceiptHandle=message.receipt, VisibilityTimeout=min(retry_delay_seconds * message.attempts, 43200))


_queue: Queue | None = None


def get_queue() -> Queue:
    global _queue
    if _queue is None:
        s = get_settings()
        if s.queue_backend == "sqs":
            if not s.sqs_queue_url:
                raise RuntimeError("QUEUE_BACKEND=sqs requires SQS_QUEUE_URL")
            _queue = SqsQueue(s.sqs_queue_url, s.aws_region)
        else:
            _queue = PostgresQueue()
    return _queue
