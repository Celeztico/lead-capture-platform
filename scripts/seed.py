import asyncio
from uuid import uuid4

from sqlalchemy import select

from app.core.database import async_session_maker
from app.models import (
    MembershipRole,
    User,
    Widget,
    WidgetStatus,
    Workspace,
    WorkspaceMembership,
    WorkspaceStatus,
)


async def seed() -> None:
    async with async_session_maker() as session:
        existing = await session.scalar(select(User).where(User.email == "demo@example.com"))
        if existing is not None:
            print("Seed data already present, skipping.")  # noqa: T201
            return

        # Create demo user
        demo_user = User(
            id=uuid4(),
            email="demo@example.com",
            display_name="Demo User",
            password_hash="$2b$12$dummy_hash_for_demo",
        )
        session.add(demo_user)

        # Create demo workspace
        demo_workspace = Workspace(
            id=uuid4(),
            name="Demo Workspace",
            status=WorkspaceStatus.ACTIVE.value,
        )
        session.add(demo_workspace)

        # Create owner membership
        membership = WorkspaceMembership(
            workspace_id=demo_workspace.id,
            user_id=demo_user.id,
            role=MembershipRole.OWNER.value,
        )
        session.add(membership)

        # Create demo widget
        demo_widget = Widget(
            id=uuid4(),
            public_id=uuid4(),
            workspace_id=demo_workspace.id,
            name="Contact Form",
            status=WidgetStatus.ACTIVE.value,
            configuration={
                "title": "Contact Us",
                "description": "Send us a message and we'll get back to you.",
                "submit_label": "Send Message",
                "success_message": "Thanks! Your message has been received.",
                "fields": [
                    {
                        "name": "name",
                        "type": "text",
                        "label": "Your Name",
                        "required": True,
                        "placeholder": "John Doe",
                    },
                    {
                        "name": "email",
                        "type": "email",
                        "label": "Email Address",
                        "required": True,
                        "placeholder": "john@example.com",
                    },
                    {
                        "name": "message",
                        "type": "textarea",
                        "label": "Message",
                        "required": True,
                        "placeholder": "How can we help you?",
                    },
                ],
            },
            config_version=1,
        )
        session.add(demo_widget)

        await session.commit()



if __name__ == "__main__":
    asyncio.run(seed())
