from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MembershipRole, User, Workspace, WorkspaceMembership


class WorkspaceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, name: str) -> Workspace:
        workspace = Workspace(name=name)
        self.session.add(workspace)
        await self.session.flush()
        return workspace

    async def get_by_id(self, workspace_id: UUID) -> Workspace | None:
        result = await self.session.execute(
            select(Workspace).where(Workspace.id == workspace_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_membership(
        self, workspace_id: UUID, user_id: UUID
    ) -> Workspace | None:
        result = await self.session.execute(
            select(Workspace)
            .join(WorkspaceMembership, Workspace.id == WorkspaceMembership.workspace_id)
            .where(
                Workspace.id == workspace_id,
                WorkspaceMembership.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self, user_id: UUID, limit: int = 20, offset: int = 0
    ) -> Sequence[Workspace]:
        result = await self.session.execute(
            select(Workspace)
            .join(WorkspaceMembership, Workspace.id == WorkspaceMembership.workspace_id)
            .where(WorkspaceMembership.user_id == user_id)
            .order_by(desc(Workspace.created_at))
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def update(self, workspace: Workspace) -> Workspace:
        await self.session.flush()
        return workspace

    async def delete(self, workspace: Workspace) -> None:
        await self.session.delete(workspace)
        await self.session.flush()


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, email: str, display_name: str | None = None, password_hash: str | None = None
    ) -> User:
        user = User(email=email, display_name=display_name, password_hash=password_hash)
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_by_id(self, user_id: UUID) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def update(self, user: User) -> User:
        await self.session.flush()
        return user


class MembershipRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, workspace_id: UUID, user_id: UUID, role: MembershipRole = MembershipRole.MEMBER
    ) -> WorkspaceMembership:
        membership = WorkspaceMembership(
            workspace_id=workspace_id, user_id=user_id, role=role
        )
        self.session.add(membership)
        await self.session.flush()
        return membership

    async def get(
        self, workspace_id: UUID, user_id: UUID
    ) -> WorkspaceMembership | None:
        result = await self.session.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_workspace(
        self, workspace_id: UUID
    ) -> Sequence[WorkspaceMembership]:
        result = await self.session.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id
            )
        )
        return result.scalars().all()

    async def list_for_user(self, user_id: UUID) -> Sequence[WorkspaceMembership]:
        result = await self.session.execute(
            select(WorkspaceMembership)
            .where(WorkspaceMembership.user_id == user_id)
            .order_by(desc(WorkspaceMembership.created_at))
        )
        return result.scalars().all()

    async def has_role(
        self, workspace_id: UUID, user_id: UUID, roles: list[MembershipRole]
    ) -> bool:
        result = await self.session.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user_id,
                WorkspaceMembership.role.in_(roles),
            )
        )
        return result.scalar_one_or_none() is not None
