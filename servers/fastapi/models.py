from sqlalchemy import Column, Integer, String, Text
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    display_name = Column(String, default="")
    role = Column(String, default="user", index=True)  # user | admin
    status = Column(String, default="pending", index=True)  # pending|approved|rejected|disabled
    created_at = Column(Integer, nullable=False)
    approved_at = Column(Integer, nullable=True)
    approved_by = Column(String, nullable=True)
    last_login_at = Column(Integer, nullable=True)
    failed_login_count = Column(Integer, default=0, server_default="0")
    locked_until = Column(Integer, nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(String, primary_key=True)
    actor_user_id = Column(String, index=True, nullable=True)
    action = Column(String, index=True, nullable=False)
    target_user_id = Column(String, index=True, nullable=True)
    meta_json = Column(Text, default="", server_default="")
    created_at = Column(Integer, nullable=False)


class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, unique=True, index=True, default="default_user")
    provider = Column(String, default="openai_compatible")
    base_url = Column(String, default="")
    api_key = Column(String, default="")
    model_name = Column(String, default="")
    # Rendered QA uses a separate multimodal endpoint. Optional so an older
    # client that omits them leaves the stored values alone.
    vision_model_name = Column(String, default="", server_default="")
    vision_base_url = Column(String, default="", server_default="")
    vision_api_key = Column(String, default="", server_default="")
    # Slide figure generation uses a separate image backend from text / vision QA.
    image_provider = Column(String, default="openrouter", server_default="openrouter")
    image_model_name = Column(String, default="", server_default="")
    image_base_url = Column(String, default="", server_default="")
    image_api_key = Column(String, default="", server_default="")
    connection_test_json = Column(String, default="", server_default="")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String, unique=True, index=True)
    user_id = Column(String, index=True, default="default_user")
    topic = Column(String, default="")
    status = Column(String, default="created")
    has_pdf = Column(Integer, default=0)
    created_at = Column(Integer)
    last_opened_at = Column(Integer, nullable=True)
