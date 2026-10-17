from motor.motor_asyncio import AsyncIOMotorClient

from afrovending.core.config import settings

client = AsyncIOMotorClient(settings.mongo_url, tz_aware=True)
db = client[settings.db_name]
