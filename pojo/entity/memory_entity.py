from sqlalchemy import BigInteger, Text, DateTime
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import Mapped, mapped_column, class_mapper
from utils.db_util import Base


class Memory(Base):
    __tablename__ = 'memory'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment='记忆ID')
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=True, comment='用户ID')
    content: Mapped[str] = mapped_column(Text, nullable=True, comment='记忆内容')
    embedding: Mapped[list[float]] = mapped_column(Vector(1024), nullable=True, comment='向量嵌入')
    create_time: Mapped[DateTime] = mapped_column(DateTime, nullable=True, comment='创建时间')

    def to_dict(self) -> dict:
        result = {}
        for c in class_mapper(self.__class__).columns:
            value = getattr(self, c.key)
            # 将 datetime 对象转换为字符串
            if c.key == 'create_time' and value is not None:
                value = str(value)
            result[c.key] = value
        return result
