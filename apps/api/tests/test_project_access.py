import pytest
from fastapi import HTTPException

from odei_api.services.project_access import require_project_access


class Collection:
    def __init__(self, document):
        self.document = document
        self.query = None

    async def find_one(self, query):
        self.query = query
        return self.document


@pytest.mark.asyncio
async def test_project_owner_is_authorized_without_membership_record():
    project = {
        "organization_id": "org-1", "project_id": "project-1", "status": "active",
        "owner_issuer": "https://identity.example/", "owner_subject": "user-1",
    }
    result = await require_project_access(
        Collection(project), Collection(None), organization_id="org-1",
        project_id="project-1", identity_issuer="https://identity.example/",
        identity_subject="user-1",
    )
    assert result is project


@pytest.mark.asyncio
async def test_active_project_member_is_authorized():
    project = {
        "organization_id": "org-1", "project_id": "project-1", "status": "active",
        "owner_issuer": "https://identity.example/", "owner_subject": "owner",
    }
    memberships = Collection({"status": "active"})
    await require_project_access(
        Collection(project), memberships, organization_id="org-1",
        project_id="project-1", identity_issuer="https://identity.example/",
        identity_subject="member",
    )
    assert memberships.query == {
        "organization_id": "org-1", "project_id": "project-1",
        "identity_issuer": "https://identity.example/", "identity_subject": "member",
        "status": "active",
    }


@pytest.mark.asyncio
async def test_unauthorized_project_is_hidden():
    project = {
        "organization_id": "org-1", "project_id": "project-1", "status": "active",
        "owner_issuer": "https://identity.example/", "owner_subject": "owner",
    }
    with pytest.raises(HTTPException) as error:
        await require_project_access(
            Collection(project), Collection(None), organization_id="org-1",
            project_id="project-1", identity_issuer="https://identity.example/",
            identity_subject="intruder",
        )
    assert error.value.status_code == 404
    assert error.value.detail["code"] == "PROJECT_NOT_FOUND"


@pytest.mark.asyncio
async def test_project_query_is_tenant_and_active_status_scoped():
    projects = Collection(None)
    with pytest.raises(HTTPException):
        await require_project_access(
            projects, Collection(None), organization_id="org-1", project_id="project-1",
            identity_issuer="https://identity.example/", identity_subject="user",
        )
    assert projects.query == {
        "organization_id": "org-1", "project_id": "project-1", "status": "active",
    }
