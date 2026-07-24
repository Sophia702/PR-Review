from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db import Base


class Repo(Base):
    __tablename__ = "repos"

    id = Column(Integer, primary_key=True)
    owner = Column(String, nullable=False)
    name = Column(String, nullable=False)

    __table_args__ = (UniqueConstraint("owner", "name", name="uq_repo_owner_name"),)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    login = Column(String, nullable=False, unique=True)
    is_bot = Column(Boolean, nullable=False, default=False)


class PullRequest(Base):
    __tablename__ = "pull_requests"

    id = Column(Integer, primary_key=True)
    github_id = Column(String, nullable=False, unique=True)
    repo_id = Column(Integer, ForeignKey("repos.id"), nullable=False, index=True)
    number = Column(Integer, nullable=False)
    title = Column(Text, nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    state = Column(String, nullable=False, index=True)  # open, closed, merged
    is_draft = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, index=True)
    merged_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    repo = relationship("Repo")
    author = relationship("User")
    reviews = relationship("Review", back_populates="pull_request")
    review_comments = relationship("ReviewComment", back_populates="pull_request")
    commits = relationship("Commit", back_populates="pull_request")

    __table_args__ = (UniqueConstraint("repo_id", "number", name="uq_pr_repo_number"),)


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True)
    github_id = Column(String, nullable=False, unique=True)
    pull_request_id = Column(Integer, ForeignKey("pull_requests.id"), nullable=False, index=True)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    state = Column(String, nullable=False)  # APPROVED, CHANGES_REQUESTED, COMMENTED, DISMISSED, PENDING
    submitted_at = Column(DateTime(timezone=True), nullable=True)

    pull_request = relationship("PullRequest", back_populates="reviews")
    reviewer = relationship("User")


class ReviewComment(Base):
    __tablename__ = "review_comments"

    id = Column(Integer, primary_key=True)
    github_id = Column(String, nullable=False, unique=True)
    pull_request_id = Column(Integer, ForeignKey("pull_requests.id"), nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)

    pull_request = relationship("PullRequest", back_populates="review_comments")
    author = relationship("User")


class Commit(Base):
    __tablename__ = "commits"

    id = Column(Integer, primary_key=True)
    github_id = Column(String, nullable=False, unique=True)  # commit oid
    pull_request_id = Column(Integer, ForeignKey("pull_requests.id"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # null: bot or unlinked commit email
    message = Column(Text, nullable=False)
    committed_at = Column(DateTime(timezone=True), nullable=False, index=True)

    pull_request = relationship("PullRequest", back_populates="commits")
    author = relationship("User")


class SyncState(Base):
    """Tracks the incremental-sync cursor per repo so we don't re-pull history on every run."""

    __tablename__ = "sync_state"

    id = Column(Integer, primary_key=True)
    repo_id = Column(Integer, ForeignKey("repos.id"), nullable=False, unique=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)

    repo = relationship("Repo")
