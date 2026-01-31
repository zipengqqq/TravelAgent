from sqlalchemy import Integer, Column, JSON
from sqlalchemy.dialects.postgresql import JSONB  # 使用JSONB类型以匹配PostgreSQL中的jsonb
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class UserProfile(Base):
    __tablename__ = 'user_profiles'

    user_id = Column(Integer, primary_key=True, nullable=False, comment='用户id')  # 主键
    profiles = Column(JSONB, comment='用户画像数据')  # 使用JSONB来匹配PostgreSQL中的jsonb类型
