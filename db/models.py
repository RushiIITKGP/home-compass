"""SQLAlchemy models for the Home Compass schema.
Run `python db/create_tables.py` once to create everything in Postgres."""

from __future__ import annotations

import os as _os
import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Must match the embedding model in mcp-property/embeddings.py —
# nomic-embed-text is 768. Changing it invalidates all stored vectors:
# run db/reset_embeddings.py, then re-embed.
EMBEDDING_DIM = int(_os.environ.get("EMBEDDING_DIM", "768"))


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


# ---------------------------------------------------------------- users --

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user")


# --------------------------------------------------------- conversations --

class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String(20))  # "user" | "assistant" | "tool"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


# ------------------------------------------------------------ listings --

class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[uuid.UUID] = _uuid_pk()
    address: Mapped[str] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(120), index=True)
    state: Mapped[str | None] = mapped_column(String(2), index=True)
    zip_code: Mapped[str | None] = mapped_column(String(10), index=True)
    price: Mapped[float | None] = mapped_column(Numeric(12, 2), index=True)
    beds: Mapped[int | None] = mapped_column(Integer, index=True)
    baths: Mapped[float | None] = mapped_column(Numeric(3, 1), index=True)
    sqft: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(60))  # e.g. "kaggle_seed"
    raw_attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    neighborhood_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("neighborhoods.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    neighborhood: Mapped["Neighborhood | None"] = relationship(back_populates="listings")
    embedding: Mapped["ListingEmbedding | None"] = relationship(
        back_populates="listing", uselist=False, cascade="all, delete-orphan"
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="listing")


class ListingEmbedding(Base):
    """Populated by mcp-property's embedding step (Phase 2) — not by the
    Phase 1 seed job, which only loads structured listing fields."""

    __tablename__ = "listing_embeddings"

    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id"), primary_key=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    embedded_text: Mapped[str] = mapped_column(Text)

    listing: Mapped["Listing"] = relationship(back_populates="embedding")


# -------------------------------------------------------- neighborhoods --

class Neighborhood(Base):
    __tablename__ = "neighborhoods"

    id: Mapped[uuid.UUID] = _uuid_pk()
    zip_code: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(2))
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6))

    listings: Mapped[list["Listing"]] = relationship(back_populates="neighborhood")
    demographics: Mapped[list["Demographics"]] = relationship(back_populates="neighborhood")
    crime_stats: Mapped[list["CrimeStat"]] = relationship(back_populates="neighborhood")
    market_stats: Mapped[list["MarketStat"]] = relationship(back_populates="neighborhood")


class Demographics(Base):
    """Populated by mcp-enrich (Census ACS API) — Phase 5."""

    __tablename__ = "demographics"

    id: Mapped[uuid.UUID] = _uuid_pk()
    neighborhood_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("neighborhoods.id"))
    median_household_income: Mapped[int | None] = mapped_column(Integer)
    population_density: Mapped[float | None] = mapped_column(Numeric(10, 2))
    median_age: Mapped[float | None] = mapped_column(Numeric(4, 1))
    commute_minutes_avg: Mapped[float | None] = mapped_column(Numeric(4, 1))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    neighborhood: Mapped["Neighborhood"] = relationship(back_populates="demographics")


class CrimeStat(Base):
    """Populated by mcp-enrich (FBI Crime Data API) — Phase 5."""

    __tablename__ = "crime_stats"

    id: Mapped[uuid.UUID] = _uuid_pk()
    neighborhood_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("neighborhoods.id"))
    year: Mapped[int] = mapped_column(Integer)
    violent_crime_count: Mapped[int | None] = mapped_column(Integer)
    property_crime_count: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    neighborhood: Mapped["Neighborhood"] = relationship(back_populates="crime_stats")


class MarketStat(Base):
    """Populated by mcp-market's batch ETL (Realtor.com / Redfin) — Phase 5."""

    __tablename__ = "market_stats"

    id: Mapped[uuid.UUID] = _uuid_pk()
    neighborhood_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("neighborhoods.id"))
    source: Mapped[str] = mapped_column(String(40))  # "realtor_com" | "redfin"
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    median_sale_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    inventory_count: Mapped[int | None] = mapped_column(Integer)
    median_days_on_market: Mapped[float | None] = mapped_column(Numeric(5, 1))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    neighborhood: Mapped["Neighborhood"] = relationship(back_populates="market_stats")


# -------------------------------------------------- compliance rules --

class ComplianceRule(Base):
    """One row per numbered rule section of an ingested rules PDF —
    the RAG source for the compliance guardrail. Embedding stored
    inline: the corpus is tiny."""

    __tablename__ = "compliance_rules"

    id: Mapped[uuid.UUID] = _uuid_pk()
    document: Mapped[str] = mapped_column(String(255), index=True)  # source PDF filename
    section: Mapped[str] = mapped_column(String(40))  # e.g. "§ 12.1"
    title: Mapped[str] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ----------------------------------------------------- recommendations --

class Recommendation(Base):
    """One row per listing surfaced to the user in a given conversation
    (A-02's Synthesis node) — confidence_score is the per-recommendation
    score from A-02, distinct from the intake confidence that gates
    retrieval in the first place."""

    __tablename__ = "recommendations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"))
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id"))
    confidence_score: Mapped[float] = mapped_column(Numeric(4, 3))  # 0.000–1.000
    rationale: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(back_populates="recommendations")
    listing: Mapped["Listing"] = relationship(back_populates="recommendations")
