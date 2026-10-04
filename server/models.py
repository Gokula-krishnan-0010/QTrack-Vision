"""SQLAlchemy models for camera frames, tracked detections and queue transitions."""
from datetime import datetime, timezone
from sqlalchemy import (BigInteger, Boolean, Column, DateTime, Enum, ForeignKey, Index,
                        Integer, JSON, Numeric, SmallInteger, String,
                        UniqueConstraint, func)
from sqlalchemy.dialects.mysql import BIGINT as MySQLBigInteger
from sqlalchemy.dialects.mysql import SMALLINT as MySQLSmallInteger
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# SQLAlchemy's generic integer types don't accept `unsigned=True`. Use the
# MySQL dialect types as variants while keeping SQLite-friendly integer keys.
ID_TYPE = BigInteger().with_variant(MySQLBigInteger(unsigned=True), "mysql").with_variant(Integer(), "sqlite")
UNSIGNED_BIGINT = BigInteger().with_variant(MySQLBigInteger(unsigned=True), "mysql")
UNSIGNED_SMALLINT = SmallInteger().with_variant(MySQLSmallInteger(unsigned=True), "mysql")


class Camera(Base):
    __tablename__ = "cameras"
    id = Column(ID_TYPE, primary_key=True, autoincrement=True)
    shop_id = Column(String(100), nullable=False, unique=True)
    display_name = Column(String(150))
    enabled = Column(Boolean, nullable=False, default=True)
    queue_roi = Column(JSON)
    queue_direction_x = Column(Numeric(8, 6))
    queue_direction_y = Column(Numeric(8, 6))
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class TrackingSession(Base):
    __tablename__ = "tracking_sessions"
    id = Column(ID_TYPE, primary_key=True, autoincrement=True)
    camera_id = Column(ID_TYPE, ForeignKey("cameras.id", ondelete="RESTRICT"), nullable=False)
    started_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    ended_at = Column(DateTime)
    reason = Column(String(64), nullable=False, default="startup")
    __table_args__ = (Index("ix_tracking_sessions_camera_started", "camera_id", "started_at"),)


class Frame(Base):
    __tablename__ = "frames"
    id = Column(ID_TYPE, primary_key=True, autoincrement=True)
    camera_id = Column(ID_TYPE, ForeignKey("cameras.id", ondelete="RESTRICT"), nullable=False)
    tracking_session_id = Column(ID_TYPE, ForeignKey("tracking_sessions.id", ondelete="RESTRICT"), nullable=False)
    sequence_no = Column(UNSIGNED_BIGINT, nullable=False)
    device_frame_id = Column(String(100))
    captured_at = Column(DateTime, nullable=False)
    received_at = Column(DateTime, nullable=False, server_default=func.now())
    image_path = Column(String(512))
    image_width = Column(UNSIGNED_SMALLINT)
    image_height = Column(UNSIGNED_SMALLINT)
    person_count = Column(UNSIGNED_SMALLINT, nullable=False, default=0)
    queue_count = Column(UNSIGNED_SMALLINT, nullable=False, default=0)
    previous_frame_id = Column(ID_TYPE, ForeignKey("frames.id", ondelete="SET NULL"))
    processing_status = Column(Enum("processed", "failed"), nullable=False, default="processed")
    error_message = Column(String(500))
    __table_args__ = (
        UniqueConstraint("camera_id", "sequence_no", name="uq_frames_camera_sequence"),
        UniqueConstraint("camera_id", "device_frame_id", name="uq_frames_camera_device_id"),
        Index("ix_frames_camera_captured", "camera_id", "captured_at"),
        Index("ix_frames_session_sequence", "tracking_session_id", "sequence_no"),
    )


class Detection(Base):
    __tablename__ = "detections"
    id = Column(ID_TYPE, primary_key=True, autoincrement=True)
    frame_id = Column(ID_TYPE, ForeignKey("frames.id", ondelete="CASCADE"), nullable=False)
    tracker_id = Column(UNSIGNED_BIGINT)
    class_id = Column(UNSIGNED_SMALLINT, nullable=False, default=0)
    confidence = Column(Numeric(6, 5), nullable=False)
    x1 = Column(Numeric(8, 7), nullable=False)
    y1 = Column(Numeric(8, 7), nullable=False)
    x2 = Column(Numeric(8, 7), nullable=False)
    y2 = Column(Numeric(8, 7), nullable=False)
    center_x = Column(Numeric(8, 7), nullable=False)
    center_y = Column(Numeric(8, 7), nullable=False)
    in_queue = Column(Boolean, nullable=False, default=False)
    queue_position = Column(Numeric(10, 6))
    __table_args__ = (Index("ix_detections_frame", "frame_id"), Index("ix_detections_tracker", "tracker_id"))


class QueueUpdate(Base):
    __tablename__ = "queue_updates"
    id = Column(ID_TYPE, primary_key=True, autoincrement=True)
    camera_id = Column(ID_TYPE, ForeignKey("cameras.id", ondelete="RESTRICT"), nullable=False)
    tracking_session_id = Column(ID_TYPE, ForeignKey("tracking_sessions.id", ondelete="RESTRICT"), nullable=False)
    previous_frame_id = Column(ID_TYPE, ForeignKey("frames.id", ondelete="CASCADE"), nullable=False)
    current_frame_id = Column(ID_TYPE, ForeignKey("frames.id", ondelete="CASCADE"), nullable=False, unique=True)
    measured_at = Column(DateTime, nullable=False)
    elapsed_seconds = Column(Numeric(10, 3), nullable=False)
    previous_queue_count = Column(UNSIGNED_SMALLINT, nullable=False)
    current_queue_count = Column(UNSIGNED_SMALLINT, nullable=False)
    queue_count_delta = Column(Integer, nullable=False)
    advanced_person_count = Column(UNSIGNED_SMALLINT, nullable=False, default=0)
    entered_queue_count = Column(UNSIGNED_SMALLINT, nullable=False, default=0)
    exited_queue_count = Column(UNSIGNED_SMALLINT, nullable=False, default=0)
    advanced_tracker_ids = Column(JSON)
    entered_tracker_ids = Column(JSON)
    exited_tracker_ids = Column(JSON)
    avg_wait_seconds = Column(Numeric(10, 2))
    exit_rate = Column(Numeric(8, 5))
    __table_args__ = (Index("ix_queue_updates_camera_time", "camera_id", "measured_at"),)

    def to_dict(self):
        return {
            "previous_frame_id": self.previous_frame_id,
            "current_frame_id": self.current_frame_id,
            "measured_at": self.measured_at.isoformat() if self.measured_at else None,
            "elapsed_seconds": float(self.elapsed_seconds or 0),
            "previous_queue_count": self.previous_queue_count,
            "current_queue_count": self.current_queue_count,
            "queue_count_delta": self.queue_count_delta,
            "advanced_person_count": self.advanced_person_count,
            "entered_queue_count": self.entered_queue_count,
            "exited_queue_count": self.exited_queue_count,
            "advanced_tracker_ids": self.advanced_tracker_ids or [],
            "entered_tracker_ids": self.entered_tracker_ids or [],
            "exited_tracker_ids": self.exited_tracker_ids or [],
            "avg_wait_seconds": float(self.avg_wait_seconds) if self.avg_wait_seconds is not None else None,
            "exit_rate": float(self.exit_rate) if self.exit_rate is not None else None,
        }
