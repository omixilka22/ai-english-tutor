import asyncio

from app.database.database import AsyncSessionLocal
from app.services.registration_service import RegistrationService


async def main():
    async with AsyncSessionLocal() as session:
        user = await RegistrationService.register_student(
            session=session,
            telegram_id=999999999,
            name="Test Telegram Student",
        )

        print("USER CREATED")
        print("User ID:", user.id)
        print("Telegram ID:", user.telegram_id)
        print("Role:", user.role)
        print("Name:", user.name)


if __name__ == "__main__":
    asyncio.run(main())