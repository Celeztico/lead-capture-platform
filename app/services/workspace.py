from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MembershipRole, User, Workspace, WorkspaceMembership
from app.repositories import (
    MembershipRepository,
    UserRepository,
    WorkspaceRepository,
)


class WorkspaceService:
    def __init__(self, session: AsyncSession):
        self.workspace_repo = WorkspaceRepository(session)
        self.user_repo = UserRepository(session)
        self.membership_repo = MembershipRepository(session)
        self.session = session

    async def create_workspace_with_owner(
        self, email: str, workspace_name: str, display_name: str | None = None
    ) -> tuple[Workspace, User]:
        """Create a workspace and its owner user in one transaction."""
        # Create or get user
        user = await self.user_repo.get_by_email(email)
        if not user:
            user = await self.user_repo.create(email=email, display_name=display_name)

        # Create workspace
        workspace = await self.workspace_repo.create(name=workspace_name)

        # Create owner membership
        await self.membership_repo.create(
            workspace_id=workspace.id, user_id=user.id, role=MembershipRole.OWNER
        )

        await self.session.flush()
        return workspace, user

    async def get_workspace(self, workspace_id: UUID, user_id: UUID) -> Workspace | None:
        return await self.workspace_repo.get_by_id_with_membership(workspace_id, user_id)

    async def list_workspaces_for_user(
        self, user_id: UUID, limit: int = 20, offset: int = 0
    ) -> Sequence[Workspace]:
        return await self.workspace_repo.list_for_user(user_id, limit, offset)

    async def user_has_role(
        self, workspace_id: UUID, user_id: UUID, roles: list[MembershipRole]
    ) -> bool:
        return await self.membership_repo.has_role(workspace_id, user_id, roles)

    async def add_member(
        self, workspace_id: UUID, user_id: UUID, role: MembershipRole = MembershipRole.MEMBER
    ) -> WorkspaceMembership | None:
        # Check if already a member
        existing = await self.membership_repo.get(workspace_id, user_id)
        if existing:
            return None
        return await self.membership_repo.create(workspace_id, user_id, role)
