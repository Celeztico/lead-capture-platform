from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.main import create_app
from app.services.widget import WidgetService
from app.services.workspace import WorkspaceService


@pytest.fixture
async def app():
    app = create_app()
    yield app


@pytest.fixture
async def client(app):
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
async def db_session():
    from app.core.database import async_session_maker
    async with async_session_maker() as session:
        yield session


@pytest.fixture
async def demo_workspace(db_session):
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
async def demo_user_token(demo_workspace):
    """Create a JWT token for the demo user."""
    workspace, user = demo_workspace
    token = create_access_token({"sub": str(user.id), "workspace_id": str(workspace.id)})
    return token, user, workspace


@pytest.fixture
async def demo_widget(db_session, demo_workspace):
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


class TestWidgetAuth:
    """Test authentication requirements for widget endpoints."""

    async def test_create_widget_requires_auth(self, client):
        """Test that creating a widget requires authentication."""
        response = await client.post(
            "/api/v1/widgets",
            json={
                "workspace_id": str(uuid4()),
                "name": "Test Widget",
                "configuration": {
                    "title": "Test",
                    "submit_label": "Submit",
                    "success_message": "Thanks!",
                    "fields": [{"name": "email", "type": "email", "label": "Email", "required": True}],
                },
            },
        )
        assert response.status_code == 401

    async def test_list_widgets_requires_auth(self, client):
        """Test that listing widgets requires authentication."""
        response = await client.get("/api/v1/widgets")
        assert response.status_code == 401

    async def test_get_widget_requires_auth(self, client):
        """Test that getting a widget requires authentication."""
        response = await client.get(f"/api/v1/widgets/{uuid4()}")
        assert response.status_code == 401

    async def test_update_widget_requires_auth(self, client):
        """Test that updating a widget requires authentication."""
        response = await client.patch(
            f"/api/v1/widgets/{uuid4()}",
            json={"name": "Updated"},
        )
        assert response.status_code == 401

    async def test_delete_widget_requires_auth(self, client):
        """Test that deleting a widget requires authentication."""
        response = await client.delete(f"/api/v1/widgets/{uuid4()}")
        assert response.status_code == 401

    async def test_get_embed_requires_auth(self, client):
        """Test that getting embed snippet requires authentication."""
        response = await client.get(f"/api/v1/widgets/{uuid4()}/embed")
        assert response.status_code == 401

    async def test_invalid_token_rejected(self, client):
        """Test that invalid tokens are rejected."""
        response = await client.get(
            "/api/v1/widgets",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code == 401


class TestWidgetCRUD:
    """Test widget CRUD operations."""

    async def test_create_widget(self, client, demo_user_token):
        """Test creating a widget."""
        token, user, workspace = demo_user_token
        response = await client.post(
            "/api/v1/widgets",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "workspace_id": str(workspace.id),
                "name": "New Widget",
                "configuration": {
                    "title": "Contact Us",
                    "submit_label": "Send",
                    "success_message": "Thanks!",
                    "fields": [
                        {"name": "name", "type": "text", "label": "Name", "required": True},
                        {"name": "email", "type": "email", "label": "Email", "required": True},
                    ],
                },
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Widget"
        assert data["workspace_id"] == str(workspace.id)
        assert data["public_id"] is not None
        assert data["status"] == "active"
        assert data["config_version"] == 1

    async def test_create_widget_wrong_workspace_forbidden(self, client, demo_user_token):
        """Test that creating a widget in another workspace is forbidden."""
        token, user, workspace = demo_user_token
        other_workspace_id = uuid4()
        response = await client.post(
            "/api/v1/widgets",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "workspace_id": str(other_workspace_id),
                "name": "Hacked Widget",
                "configuration": {
                    "title": "Test",
                    "submit_label": "Go",
                    "success_message": "Done",
                    "fields": [{"name": "email", "type": "email", "label": "Email", "required": True}],
                },
            },
        )
        assert response.status_code == 403

    async def test_list_widgets(self, client, demo_user_token, demo_widget):
        """Test listing widgets."""
        token, user, workspace = demo_user_token
        response = await client.get(
            "/api/v1/widgets",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) >= 1
        widget_names = [w["name"] for w in data["items"]]
        assert "Test Widget" in widget_names

    async def test_list_widgets_pagination(self, client, demo_user_token, demo_widget):
        """Test pagination on widget list."""
        token, user, workspace = demo_user_token
        response = await client.get(
            "/api/v1/widgets?limit=1&offset=0",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 1

    async def test_get_widget(self, client, demo_user_token, demo_widget):
        """Test getting a single widget."""
        token, user, workspace = demo_user_token
        response = await client.get(
            f"/api/v1/widgets/{demo_widget.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(demo_widget.id)
        assert data["name"] == demo_widget.name

    async def test_get_widget_not_found(self, client, demo_user_token):
        """Test getting a non-existent widget returns 404."""
        token, user, workspace = demo_user_token
        response = await client.get(
            f"/api/v1/widgets/{uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    async def test_update_widget(self, client, demo_user_token, demo_widget):
        """Test updating a widget."""
        token, user, workspace = demo_user_token
        response = await client.patch(
            f"/api/v1/widgets/{demo_widget.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Updated Widget Name"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Widget Name"

    async def test_update_widget_status(self, client, demo_user_token, demo_widget):
        """Test updating widget status."""
        token, user, workspace = demo_user_token
        response = await client.patch(
            f"/api/v1/widgets/{demo_widget.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"status": "disabled"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "disabled"

    async def test_update_widget_configuration(self, client, demo_user_token, demo_widget):
        """Test updating widget configuration."""
        token, user, workspace = demo_user_token
        response = await client.patch(
            f"/api/v1/widgets/{demo_widget.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "configuration": {
                    "title": "Updated Title",
                    "submit_label": "Send Now",
                    "success_message": "Received!",
                    "fields": [
                        {"name": "email", "type": "email", "label": "Email", "required": True}
                    ],
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["configuration"]["title"] == "Updated Title"
        assert data["config_version"] == 2  # Version should increment

    async def test_delete_widget(self, client, demo_user_token, demo_widget):
        """Test deleting a widget."""
        token, user, workspace = demo_user_token
        response = await client.delete(
            f"/api/v1/widgets/{demo_widget.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 204

        # Verify it's gone
        response = await client.get(
            f"/api/v1/widgets/{demo_widget.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    async def test_get_embed_snippet(self, client, demo_user_token, demo_widget):
        """Test getting embed snippet."""
        token, user, workspace = demo_user_token
        response = await client.get(
            f"/api/v1/widgets/{demo_widget.id}/embed",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "snippet" in data
        assert "script_url" in data
        assert str(demo_widget.public_id) in data["snippet"]
        assert "lead-capture-widget" in data["snippet"]


class TestCrossTenantIsolation:
    """Test that tenants cannot access each other's data."""

    async def test_cannot_list_other_tenant_widgets(self, client, db_session):
        """Test that a user cannot list widgets from another workspace."""
        from app.services.widget import WidgetService
        from app.services.workspace import WorkspaceService

        # Create two workspaces with different users
        service = WorkspaceService(db_session)
        workspace1, user1 = await service.create_workspace_with_owner(
            email="user1@example.com", workspace_name="Workspace 1"
        )
        workspace2, user2 = await service.create_workspace_with_owner(
            email="user2@example.com", workspace_name="Workspace 2"
        )

        # Create widgets in each workspace
        widget_service = WidgetService(db_session)
        await widget_service.create_widget(
            workspace_id=workspace1.id, name="Widget 1", configuration={}
        )
        await widget_service.create_widget(
            workspace_id=workspace2.id, name="Widget 2", configuration={}
        )
        await db_session.commit()

        # Create tokens for each user
        from app.core.security import create_access_token
        token1 = create_access_token({"sub": str(user1.id), "workspace_id": str(workspace1.id)})
        token2 = create_access_token({"sub": str(user2.id), "workspace_id": str(workspace2.id)})

        # User 1 should only see their widget
        from httpx import AsyncClient
        async with AsyncClient(app=create_app(), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/widgets",
                headers={"Authorization": f"Bearer {token1}"},
            )
            assert response.status_code == 200
            data = response.json()
            widget_names = [w["name"] for w in data["items"]]
            assert "Widget 1" in widget_names
            assert "Widget 2" not in widget_names

            # User 2 should only see their widget
            response = await client.get(
                "/api/v1/widgets",
                headers={"Authorization": f"Bearer {token2}"},
            )
            assert response.status_code == 200
            data = response.json()
            widget_names = [w["name"] for w in data["items"]]
            assert "Widget 2" in widget_names
            assert "Widget 1" not in widget_names

    async def test_cannot_access_other_tenant_widget(self, client, db_session):
        """Test that a user cannot access a widget from another workspace."""
        from app.core.security import create_access_token
        from app.services.widget import WidgetService
        from app.services.workspace import WorkspaceService

        service = WorkspaceService(db_session)
        workspace1, user1 = await service.create_workspace_with_owner(
            email="user1@example.com", workspace_name="Workspace 1"
        )
        workspace2, user2 = await service.create_workspace_with_owner(
            email="user2@example.com", workspace_name="Workspace 2"
        )

        widget_service = WidgetService(db_session)
        widget2 = await widget_service.create_widget(
            workspace_id=workspace2.id, name="Widget 2", configuration={}
        )
        await db_session.commit()

        token1 = create_access_token({"sub": str(user1.id), "workspace_id": str(workspace1.id)})

        async with AsyncClient(app=create_app(), base_url="http://test") as client:
            # User 1 tries to access User 2's widget
            response = await client.get(
                f"/api/v1/widgets/{widget2.id}",
                headers={"Authorization": f"Bearer {token1}"},
            )
            assert response.status_code == 404

            # User 1 tries to update User 2's widget
            response = await client.patch(
                f"/api/v1/widgets/{widget2.id}",
                headers={"Authorization": f"Bearer {token1}"},
                json={"name": "Hacked"},
            )
            assert response.status_code == 404

            # User 1 tries to delete User 2's widget
            response = await client.delete(
                f"/api/v1/widgets/{widget2.id}",
                headers={"Authorization": f"Bearer {token1}"},
            )
            assert response.status_code == 404


class TestWidgetValidation:
    """Test widget validation."""

    async def test_create_widget_invalid_configuration(self, client, demo_user_token):
        """Test that invalid widget configuration is rejected."""
        token, user, workspace = demo_user_token
        response = await client.post(
            "/api/v1/widgets",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "workspace_id": str(workspace.id),
                "name": "Invalid Widget",
                "configuration": {
                    "title": "Test",
                    "submit_label": "Go",
                    "success_message": "Done",
                    "fields": [
                        {"name": "email", "type": "invalid_type", "label": "Email", "required": True}
                    ],
                },
            },
        )
        assert response.status_code == 422

    async def test_create_widget_missing_required_fields(self, client, demo_user_token):
        """Test that missing required fields are rejected."""
        token, user, workspace = demo_user_token
        response = await client.post(
            "/api/v1/widgets",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "workspace_id": str(workspace.id),
                "name": "Invalid Widget",
                "configuration": {
                    "title": "Test",
                    "submit_label": "Go",
                    "success_message": "Done",
                    "fields": [],
                },
            },
        )
        assert response.status_code == 422

    async def test_update_widget_invalid_status(self, client, demo_user_token, demo_widget):
        """Test that invalid status is rejected."""
        token, user, workspace = demo_user_token
        response = await client.patch(
            f"/api/v1/widgets/{demo_widget.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"status": "invalid_status"},
        )
        assert response.status_code == 422
