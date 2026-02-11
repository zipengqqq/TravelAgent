from sqlalchemy import BigInteger, Date, String
from sqlalchemy.orm import Mapped, mapped_column, class_mapper
from utils.db_util import Base


class Conversation(Base):
    __tablename__ = 'conversation'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment='主键')
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=True, comment='用户id')
    thread_id: Mapped[int] = mapped_column(BigInteger, nullable=True, comment='会话id')
    create_time: Mapped[Date] = mapped_column(Date, nullable=True, comment='创建时间')
    name: Mapped[str] = mapped_column(String, nullable=True, comment='对话名称')

    def to_dict(self) -> dict:
        result = {}
        for c in class_mapper(self.__class__).columns:
            value = getattr(self, c.key)
            # 将 datetime 对象转换为字符串
            if c.key == 'create_time' and value is not None:
                value = str(value)
            if (c.key == 'id' or c.key.endswith('id')) and value is not None:
                value = str(value)
            result[c.key] = value
        return result
