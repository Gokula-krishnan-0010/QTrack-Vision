"""
QTrack Vision — SQLAlchemy models.

Schema for frame_records: stores metadata and analytics for every
frame received from an ESP32-CAM device.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class FrameRecord(Base):
    """
    One row per frame received from an ESP32-CAM.

    Columns:
        shop_id       – Identifier of the shop / camera location
        timestamp     – Epoch time the frame was captured (from ESP32)
        file_path     – Relative path to the saved JPEG on disk
        person_count  – Total persons detected in the frame
        queue_length  – Persons inside the defined queue zone
        avg_wait_sec  – Estimated average wait time (seconds)
        exit_rate     – Fraction of tracked persons who left recently
        created_at    – Server-side receive time
    """

    __tablename__ = "frame_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shop_id = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False)
    file_path = Column(String, nullable=False)
    person_count = Column(Integer, default=0)
    queue_length = Column(Integer, default=0)
    avg_wait_sec = Column(Float, default=0.0)
    exit_rate = Column(Float, default=0.0)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self) -> dict:
        """Serialize for JSON / SSE payloads."""
        return {
            "id": self.id,
            "shop_id": self.shop_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "person_count": self.person_count,
            "queue_length": self.queue_length,
            "avg_wait_sec": self.avg_wait_sec,
            "exit_rate": self.exit_rate,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
