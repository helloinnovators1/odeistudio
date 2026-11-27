from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from odei_api.services.project_lifecycle import fence_project_write


@pytest.mark.asyncio
async def test_project_write_fence_updates_active_project_in_calling_transaction():
    projects = Mock()
    projects.update_one = AsyncMock(return_value=Mock(matched_count=1))
    session = object()

    await fence_project_write(
        projects, organization_id="org-a", project_id="project-a", session=session,
    )

    projects.update_one.assert_awaited_once_with(
        {"organization_id": "org-a", "project_id": "project-a", "status": "active"},
        {"$inc": {"lifecycle_write_seq": 1}},
        session=session,
    )


@pytest.mark.asyncio
async def test_project_write_fence_rejects_missing_or_deleting_project():
    projects = Mock()
    projects.update_one = AsyncMock(return_value=Mock(matched_count=0))

    with pytest.raises(HTTPException) as raised:
        await fence_project_write(
            projects, organization_id="org-a", project_id="project-a", session=object(),
        )

    assert raised.value.status_code == 409
    assert raised.value.detail["code"] == "PROJECT_LIFECYCLE_CLOSED"


@pytest.mark.asyncio
async def test_project_write_fence_requires_transaction_session():
    projects = Mock()
    projects.update_one = AsyncMock()

    with pytest.raises(ValueError):
        await fence_project_write(
            projects, organization_id="org-a", project_id="project-a", session=None,
        )

    projects.update_one.assert_not_awaited()
