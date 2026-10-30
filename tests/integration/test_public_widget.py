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
        email="public_test@example.com",
        workspace_name="Public Test Workspace",
        display_name="Public Test User",
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
        name="Public Test Widget",
        configuration={
            "title": "Contact Us",
            "submit_label": "Send Message",
            "success_message": "Thanks!",
            "fields": [
                {"name": "name", "type": "text", "label": "Your Name", "required": True},
                {"name": "email", "type": "email", "label": "Email Address", "required": True},
            ],
        },
    )
    await db_session.commit()
    return widget


class TestStaticWidgetServing:
    """Test static widget JavaScript asset serving."""

    async def test_widget_js_served(self, client):
        """Test that the widget JavaScript file is served from /widget/v1/widget.js."""
        response = await client.get("/widget/v1/widget.js")
        assert response.status_code == 200
        assert "application/javascript" in response.headers.get("content-type", "")
        assert "Lead-Capture Platform" in response.text
        assert "data-widget-id" in response.text

    async def test_widget_js_has_cache_headers(self, client):
        """Test that static widget JS has cache headers for immutable assets."""
        response = await client.get("/widget/v1/widget.js")
        assert response.status_code == 200
        cache_control = response.headers.get("cache-control", "")
        assert "public" in cache_control
        assert "max-age" in cache_control

    async def test_widget_js_not_found_for_v2(self, client):
        """Test that v2 path does not exist yet (future breaking changes)."""
        response = await client.get("/widget/v2/widget.js")
        assert response.status_code == 404


class TestPublicConfigEndpoint:
    """Test public widget configuration endpoint with ETag and cache headers."""

    async def test_public_config_returns_200(self, client, demo_widget):
        """Test that public config endpoint returns 200 for active widget."""
        response = await client.get(f"/public/v1/widgets/{demo_widget.public_id}/config")
        assert response.status_code == 200
        data = response.json()
        assert data["public_widget_id"] == str(demo_widget.public_id)
        assert data["status"] == "active"
        assert data["config_version"] == 1
        assert "configuration" in data

    async def test_public_config_returns_etag(self, client, demo_widget):
        """Test that public config response includes weak ETag."""
        response = await client.get(f"/public/v1/widgets/{demo_widget.public_id}/config")
        assert response.status_code == 200
        etag = response.headers.get("etag")
        assert etag is not None
        assert etag == f'W/"{demo_widget.config_version}"'

    async def test_public_config_cache_headers(self, client, demo_widget):
        """Test that public config response includes cache headers."""
        response = await client.get(f"/public/v1/widgets/{demo_widget.public_id}/config")
        assert response.status_code == 200
        cache_control = response.headers.get("cache-control", "")
        assert "public" in cache_control
        assert "max-age=60" in cache_control
        assert "stale-while-revalidate=300" in cache_control

    async def test_public_config_vary_header(self, client, demo_widget):
        """Test that public config response includes Vary: Origin header."""
        response = await client.get(
            f"/public/v1/widgets/{demo_widget.public_id}/config",
            headers={"Origin": "http://example.com"},
        )
        assert response.status_code == 200
        vary = response.headers.get("vary", "")
        assert "Origin" in vary

    async def test_public_config_304_on_etag_match(self, client, demo_widget):
        """Test that conditional request with matching ETag returns 304."""
        # First request to get ETag
        response1 = await client.get(f"/public/v1/widgets/{demo_widget.public_id}/config")
        assert response1.status_code == 200
        etag = response1.headers.get("etag")

        # Second request with If-None-Match
        response2 = await client.get(
            f"/public/v1/widgets/{demo_widget.public_id}/config",
            headers={"If-None-Match": etag},
        )
        assert response2.status_code == 304

    async def test_public_config_200_on_etag_mismatch(self, client, demo_widget):
        """Test that conditional request with non-matching ETag returns 200."""
        response = await client.get(
            f"/public/v1/widgets/{demo_widget.public_id}/config",
            headers={"If-None-Match": 'W/"999"'},
        )
        assert response.status_code == 200

    async def test_public_config_unknown_widget_404(self, client):
        """Test that unknown public widget ID returns 404."""
        import uuid
        response = await client.get(f"/public/v1/widgets/{uuid.uuid4()}/config")
        assert response.status_code == 404

    async def test_public_config_disabled_widget_404(self, client, db_session, demo_workspace):
        """Test that disabled widget returns 404 from public endpoint."""
        from app.models import WidgetStatus
        workspace, user = demo_workspace
        service = WidgetService(db_session)
        widget = await service.create_widget(
            workspace_id=workspace.id,
            name="Disabled Widget",
            configuration={
                "title": "Disabled",
                "submit_label": "Submit",
                "success_message": "Thanks!",
                "fields": [{"name": "email", "type": "email", "label": "Email", "required": True}],
            },
        )
        await service.update_widget(
            widget_id=widget.id,
            workspace_id=workspace.id,
            status=WidgetStatus.DISABLED,
        )
        await db_session.commit()

        response = await client.get(f"/public/v1/widgets/{widget.public_id}/config")
        assert response.status_code == 404

    async def test_public_config_no_private_fields(self, client, demo_widget):
        """Test that public config does not expose private workspace data."""
        response = await client.get(f"/public/v1/widgets/{demo_widget.public_id}/config")
        assert response.status_code == 200
        data = response.json()

        # Should not contain workspace_id, internal IDs, or secrets
        assert "workspace_id" not in data
        assert "id" not in data  # Internal widget ID should not be exposed
        assert "secret" not in str(data).lower()
        assert "token" not in str(data).lower()

        # Public fields should be present
        assert "public_widget_id" in data
        assert "config_version" in data
        assert "configuration" in data


class TestEmbedSnippetURLGeneration:
    """Test embed snippet URL generation uses PUBLIC_BASE_URL."""

    async def test_embed_snippet_uses_public_base_url(self, client, demo_user_token, demo_widget):
        """Test that embed snippet references PUBLIC_BASE_URL."""
        token, user, workspace = demo_user_token
        response = await client.get(
            f"/api/v1/widgets/{demo_widget.id}/embed",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()

        # script_url should use PUBLIC_BASE_URL (default: http://localhost:8000)
        assert data["script_url"] == "http://localhost:8000/widget/v1/widget.js"
        assert "/widget/v1/widget.js" in data["script_url"]
        assert "widget.1.js" not in data["script_url"]  # Old pattern should not appear

        # Snippet should reference the correct script URL
        assert data["script_url"] in data["snippet"]
        assert str(demo_widget.public_id) in data["snippet"]
        assert 'data-widget-id="' in data["snippet"]
        assert "defer" in data["snippet"]

    async def test_embed_snippet_requires_auth(self, client, demo_widget):
        """Test that embed snippet endpoint requires authentication."""
        response = await client.get(f"/api/v1/widgets/{demo_widget.id}/embed")
        assert response.status_code == 401


class TestConfigVersionIncrement:
    """Test that config_version increments on configuration updates."""

    async def test_config_version_increments_on_update(self, client, demo_user_token, demo_widget):
        """Test that updating widget configuration increments config_version."""
        token, user, workspace = demo_user_token
        assert demo_widget.config_version == 1

        # Update configuration
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
        assert data["config_version"] == 2  # Should increment from 1

    async def test_config_version_increments_on_name_update(self, client, demo_user_token, demo_widget):
        """Test that updating widget name does NOT increment config_version (only config changes)."""
        token, user, workspace = demo_user_token

        # Update only name - config_version should stay the same
        response = await client.patch(
            f"/api/v1/widgets/{demo_widget.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "New Name Only"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["config_version"] == 1  # Name change doesn't bump config version

    async def test_config_version_reflected_in_public_config(self, client, demo_user_token, demo_widget):
        """Test that config_version increment is reflected in public config ETag."""
        token, user, workspace = demo_user_token

        # Get initial ETag
        response1 = await client.get(f"/public/v1/widgets/{demo_widget.public_id}/config")
        assert response1.status_code == 200
        etag1 = response1.headers.get("etag")
        assert etag1 == 'W/"1"'

        # Update configuration
        await client.patch(
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

        # Get new ETag - should reflect incremented version
        response2 = await client.get(f"/public/v1/widgets/{demo_widget.public_id}/config")
        assert response2.status_code == 200
        etag2 = response2.headers.get("etag")
        assert etag2 == 'W/"2"'
        assert etag1 != etag2


class TestCrossTenantPublicConfig:
    """Test tenant isolation for public widget configuration."""

    async def test_tenant_a_cannot_see_tenant_b_config(self, client, db_session):
        """Test that public config is scoped to correct widget/workspace."""
        from app.services.widget import WidgetService
        from app.services.workspace import WorkspaceService

        # Create two workspaces
        service = WorkspaceService(db_session)
        workspace_a, user_a = await service.create_workspace_with_owner(
            email="tenant_a@example.com", workspace_name="Tenant A"
        )
        workspace_b, user_b = await service.create_workspace_with_owner(
            email="tenant_b@example.com", workspace_name="Tenant B"
        )

        # Create widgets in each workspace
        widget_service = WidgetService(db_session)
        valid_config = {
            "title": "Tenant Form",
            "submit_label": "Submit",
            "success_message": "Thanks!",
            "fields": [{"name": "email", "type": "email", "label": "Email", "required": True}],
        }
        widget_a = await widget_service.create_widget(
            workspace_id=workspace_a.id, name="Widget A", configuration=valid_config
        )
        widget_b = await widget_service.create_widget(
            workspace_id=workspace_b.id, name="Widget B", configuration=valid_config
        )
        await db_session.commit()

        # Each widget's public config should return its own data
        response_a = await client.get(f"/public/v1/widgets/{widget_a.public_id}/config")
        assert response_a.status_code == 200
        assert response_a.json()["public_widget_id"] == str(widget_a.public_id)

        response_b = await client.get(f"/public/v1/widgets/{widget_b.public_id}/config")
        assert response_b.status_code == 200
        assert response_b.json()["public_widget_id"] == str(widget_b.public_id)

        # Tenant A's widget public_id should not match Tenant B's
        assert str(widget_a.public_id) != str(widget_b.public_id)


class TestCORSConfiguration:
    """Test CORS behavior for public widget endpoints."""

    async def test_public_config_cors_headers(self, client, demo_widget):
        """Test that public config endpoint returns CORS headers."""
        response = await client.get(
            f"/public/v1/widgets/{demo_widget.public_id}/config",
            headers={"Origin": "http://example.com"},
        )
        assert response.status_code == 200
        # CORS headers should be present
        assert "access-control-allow-origin" in response.headers

    async def test_widget_js_cors_headers(self, client):
        """Test that widget JS asset returns CORS headers."""
        response = await client.get(
            "/widget/v1/widget.js",
            headers={"Origin": "http://example.com"},
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers

    async def test_options_preflight_for_public_config(self, client, demo_widget):
        """Test CORS preflight OPTIONS request for public config endpoint."""
        response = await client.options(
            f"/public/v1/widgets/{demo_widget.public_id}/config",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200

    async def test_options_preflight_for_widget_js(self, client):
        """Test CORS preflight OPTIONS request for widget JS asset."""
        response = await client.options(
            "/widget/v1/widget.js",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
