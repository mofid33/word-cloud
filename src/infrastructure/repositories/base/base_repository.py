from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import DeclarativeBase

from src.infrastructure.context.sql_db.psql_dbcontext import PsqlDbContext


TModel = TypeVar("TModel", bound=DeclarativeBase)


class BaseRepository(Generic[TModel]):
    def __init__(self, db_context: PsqlDbContext, model: type[TModel]):
        self._db_context = db_context
        self._model = model

    async def insert_async(self, entity: TModel) -> TModel:
        async with self._db_context.session() as session:
            session.add(entity)
            await session.commit()
            await session.refresh(entity)
            return entity

    async def insert_and_get_id_async(self, entity: TModel):
        saved = await self.insert_async(entity)
        return getattr(saved, "id")

    async def get_by_id_async(self, entity_id: object) -> TModel | None:
        async with self._db_context.session() as session:
            return await session.get(self._model, entity_id)

    async def get_all_async(self) -> list[TModel]:
        async with self._db_context.session() as session:
            result = await session.execute(select(self._model))
            return list(result.scalars().all())

    async def update_async(self, entity: TModel) -> TModel:
        async with self._db_context.session() as session:
            merged = await session.merge(entity)
            await session.commit()
            await session.refresh(merged)
            return merged

    async def delete_async(self, entity_id: object) -> bool:
        async with self._db_context.session() as session:
            entity = await session.get(self._model, entity_id)
            if entity is None:
                return False
            await session.delete(entity)
            await session.commit()
            return True
