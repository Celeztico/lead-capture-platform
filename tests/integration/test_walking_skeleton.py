
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker, init_db
from app.main import create_app
from app.models import MembershipRole, Widget, WidgetStatus
from app.services.widget import WidgetService
from app.services.workspace import WorkspaceService


@pytest.fixture
async def app():
    app = create_app()
    await init_db()
    yield app


@pytest.fixture
async def client(app):
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
async def db_session():
    async with async_session_maker() as session:
        yield session


@pytest.fixture
async def demo_workspace(db_session: AsyncSession):
    """Create a demo workspace with user for testing."""
    service = WorkspaceService(db_session)
    workspace, user = await service.create_workspace_with_owner(
        email="test@example.com",
        workspace_name="Test Workspace",
        display_name="Test User",
    )
    await db_session.commit()
    return workspace, user


@pytest.fixture
async def demo_widget(db_session: AsyncSession, demo_workspace):
    """Create a demo widget for testing."""
    workspace, user = demo_workspace
    service = WidgetService(db_session)
    widget = await service.create_widget(
        workspace_id=workspace.id,
        name="Test Widget",
        configuration={
            "title": "Test Form",
            "submit_label": "Submit",
            "success_message": "Thanks!",
            "fields": [
                {"name": "name", "type": "text", "label": "Name", "required": True},
                {"name": "email", "type": "email", "label": "Email", "required": True},
            ],
        },
    )
    await db_session.commit()
    return widget


class TestWalkingSkeleton:
    """Integration tests for the walking skeleton - basic CRUD with database."""

    async def test_health_endpoints(self, client):
        """Test that health endpoints work."""
        # Liveness
        response = await client.get("/api/v1/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}

        # Readiness (should work after DB init)
        response = await client.get("/api/v1/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["database"] == "connected"

    async def test_workspace_creation(self, db_session: AsyncSession):
        """Test workspace and user creation."""
        service = WorkspaceService(db_session)
        workspace, user = await service.create_workspace_with_owner(
            email="newuser@example.com",
            workspace_name="New Workspace",
        )
        await db_session.commit()

        assert workspace.id is not None
        assert workspace.name == "New Workspace"
        assert user.email == "newuser@example.com"

        # Verify membership
        memberships = await service.membership_repo.list_for_workspace(workspace.id)
        assert len(memberships) == 1
        assert memberships[0].role == MembershipRole.OWNER

    async def test_widget_creation(self, db_session: AsyncSession, demo_workspace):
        """Test widget creation."""
        workspace, user = demo_workspace
        service = WidgetService(db_session)

        widget = await service.create_widget(
            workspace_id=workspace.id,
            name="Integration Test Widget",
            configuration={
                "title": "Test",
                "submit_label": "Go",
                "success_message": "Done",
                "fields": [{"name": "email", "type": "email", "label": "Email", "required": True}],
            },
        )
        await db_session.commit()

        assert widget.id is not None
        assert widget.public_id is not None
        assert widget.workspace_id == workspace.id
        assert widget.status == WidgetStatus.ACTIVE
        assert widget.config_version == 1

    async def test_widget_retrieval(self, db_session: AsyncSession, demo_widget):
        """Test widget retrieval by ID and public ID."""
        service = WidgetService(db_session)

        # By internal ID
        widget = await service.get_widget(demo_widget.id, demo_widget.workspace_id)
        assert widget is not None
        assert widget.id == demo_widget.id

        # By public ID
        widget = await service.get_widget_by_public_id(demo_widget.public_id)
        assert widget is not None
        assert widget.public_id == demo_widget.public_id

    async def test_public_config_endpoint(self, client, demo_widget):
        """Test public widget config endpoint."""
        response = await client.get(f"/public/v1/widgets/{demo_widget.public_id}/config")
        assert response.status_code == 200
        data = response.json()
        assert data["public_widget_id"] == str(demo_widget.public_id)
        assert data["status"] == "active"
        assert "configuration" in data
        assert "fields" in data["configuration"]

    async def test_database_persistence(self, db_session: AsyncSession, demo_widget):
        """Test that data persists correctly."""
        # Verify widget exists in database
        from sqlalchemy import select
        result = await db_session.execute(select(Widget).where(Widget.id == demo_widget.id))
        widget = result.scalar_one_or_none()
        assert widget is not None
        assert widget.name == demo_widget.name
