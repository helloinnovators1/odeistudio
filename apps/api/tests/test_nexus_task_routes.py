from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from odei_api.main import app
from odei_api.security.auth import Principal, get_current_principal
from odei_api.services.tasks import TaskRecord, TaskStatus, identity_owner_key, transition_task


class Collection:
    def __init__(self, document=None):
        self.document = document
        self.query = None

    async def find_one(self, query):
        self.query = query
        return self.document


class Database:
    def __init__(self):
        self.collections = {
            "organization_memberships": Collection({"status": "active"}),
            "projects": Collection({
                "organization_id": "org-1", "project_id": "project-1",
                "status": "active", "owner_issuer": "https://identity.example/",
                "owner_subject": "user-1",
            }),
            "project_memberships": Collection(None),
        }

    def __getitem__(self, name):
        return self.collections[name]


class Audit:
    def __init__(self):
        self.events = []

    async def append(self, **event):
        self.events.append(event)


class ConversationStore:
    def __init__(self):
        self.documents = {}

    async def create(self, *, organization_id, project_id, owner_issuer, owner_subject, title):
        now = datetime.now(timezone.utc)
        document = {
            "conversation_id": uuid4().hex, "organization_id": organization_id,
            "project_id": project_id, "owner_issuer": owner_issuer,
            "owner_subject": owner_subject, "title": title, "messages": [],
            "version": 0, "created_at": now, "updated_at": now,
        }
        self.documents[document["conversation_id"]] = document
        return document

    async def list_for_owner(self, *, organization_id, project_id, owner_issuer, owner_subject, limit=30):
        return [
            item for item in self.documents.values()
            if item["organization_id"] == organization_id
            and item["project_id"] == project_id
            and item["owner_issuer"] == owner_issuer
            and item["owner_subject"] == owner_subject
        ][:limit]

    async def get_for_owner(self, *, organization_id, project_id, owner_issuer, owner_subject, conversation_id):
        item = self.documents.get(conversation_id)
        if not item or item["organization_id"] != organization_id or item["project_id"] != project_id or item["owner_issuer"] != owner_issuer or item["owner_subject"] != owner_subject:
            return None
        return item

    async def delete_for_owner(self, *, organization_id, project_id, owner_issuer, owner_subject, conversation_id):
        item = await self.get_for_owner(
            organization_id=organization_id, project_id=project_id,
            owner_issuer=owner_issuer, owner_subject=owner_subject,
            conversation_id=conversation_id,
        )
        if item is None:
            return False
        del self.documents[conversation_id]
        return True

    async def append(self, *, organization_id, project_id, owner_issuer, owner_subject, conversation_id, role, content, expected_version=None):
        item = await self.get_for_owner(
            organization_id=organization_id, project_id=project_id,
            owner_issuer=owner_issuer, owner_subject=owner_subject,
            conversation_id=conversation_id,
        )
        if item is None or (expected_version is not None and item["version"] != expected_version):
            return None
        message = {
            "message_id": uuid4().hex, "role": role, "content": content,
            "created_at": datetime.now(timezone.utc),
        }
        item["messages"].append(message)
        item["version"] += 1
        item["updated_at"] = message["created_at"]
        return item





class PatchProposalStore:
    def __init__(self):
        self.documents = {}

    async def create(self, *, organization_id, project_id, owner_issuer, owner_subject, title, files, proposal_id=None):
        now = datetime.now(timezone.utc)
        item = {
            "proposal_id": proposal_id or uuid4().hex,
            "organization_id": organization_id,
            "project_id": project_id,
            "owner_issuer": owner_issuer,
            "owner_subject": owner_subject,
            "title": title,
            "files": files,
            "status": "pending",
            "version": 0,
            "created_at": now,
            "updated_at": now,
            "decided_by_issuer": None,
            "decided_by_subject": None,
            "decided_at": None,
        }
        self.documents[item["proposal_id"]] = item
        return item


class TaskStore:
    def __init__(self, audit):
        self.tasks = {}
        self.audit = audit

    async def create_planned(self, task, *, plan, audit_event=None):
        current = task
        for status in (TaskStatus.CONTEXT_GATHERING, TaskStatus.PLANNING, TaskStatus.AWAITING_APPROVAL):
            current = transition_task(
                current, status, expected_version=current.version,
                plan=plan if status is TaskStatus.AWAITING_APPROVAL else None,
            )
        self.tasks[current.id] = current
        if audit_event is not None:
            await self.audit.append(**audit_event)
        return current

    async def list_events(self, *, organization_id, task_id, after_version=-1, limit=50):
        task = await self.get(organization_id=organization_id, task_id=task_id)
        if task is None:
            return [], False
        rows = [
            {"event_id": f"event-{version}", "type": "task.status_changed",
             "version": version, "from_status": "planning",
             "to_status": "awaiting_approval", "occurred_at": datetime.now(timezone.utc)}
            for version in range(4) if version > after_version
        ]
        return rows[:limit], len(rows) > limit

    async def get(self, *, organization_id, task_id):
        task = self.tasks.get(task_id)
        return task if task and task.organization_id == organization_id else None

    async def transition(self, *, organization_id, task_id, next_status, expected_version, actor_id=None, audit_event=None):
        current = await self.get(organization_id=organization_id, task_id=task_id)
        if current is None:
            raise KeyError("Task not found")
        updated = transition_task(current, next_status, expected_version=expected_version)
        self.tasks[task_id] = updated
        if audit_event is not None:
            await self.audit.append(**audit_event)
        return updated


@pytest.fixture
def route_state():
    previous = {
        key: getattr(app.state, key, None)
        for key in ("mongo_database", "audit_event_store", "task_store", "conversation_store", "patch_proposal_store")
    }
    database, audit = Database(), Audit()
    tasks = TaskStore(audit)
    app.state.mongo_database = database
    app.state.audit_event_store = audit
    app.state.task_store = tasks
    conversations = ConversationStore()
    app.state.conversation_store = conversations
    proposals = PatchProposalStore()
    app.state.patch_proposal_store = proposals
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="user-1", issuer="https://identity.example/",
    )
    try:
        yield database, audit, tasks, conversations
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
        for key, value in previous.items():
            setattr(app.state, key, value)


def test_project_task_requires_cloud_consent(route_state):
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks",
        json={"task": "Add tests", "cloud_model_consent": False},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "CLOUD_MODEL_CONSENT_REQUIRED"


def test_project_task_requires_active_project_access(route_state, monkeypatch):
    database, audit, _, _ = route_state
    database.collections["projects"].document = None
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks",
        json={"task": "Add tests", "cloud_model_consent": True},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
    assert len(audit.events) == 1
    assert audit.events[0]["action"] == "nexus.project.access"
    assert audit.events[0]["outcome"] == "denied"
    assert audit.events[0]["target_id"] == "project-1"


def test_project_task_is_persisted_for_approval_and_audited(route_state, monkeypatch):
    _, audit, tasks, _ = route_state
    monkeypatch.setattr("odei_api.services.nexus_tasks.get_openai_client", lambda: (object(), "model"))
    monkeypatch.setattr(
        "odei_api.services.nexus_tasks.create_task_plan",
        lambda *_args, **_kwargs: SimpleNamespace(text="Inspect, implement, verify", model="model"),
    )
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks",
        json={"task": "Add tests", "cloud_model_consent": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "awaiting_approval"
    assert body["version"] == 3
    assert body["plan"] == "Inspect, implement, verify"
    assert tasks.tasks[body["task_id"]].status is TaskStatus.AWAITING_APPROVAL
    assert audit.events[0]["action"] == "nexus.task.create"
    assert audit.events[0]["outcome"] == "success"
    assert "Add tests" not in str(audit.events)


def test_approval_records_approval_without_starting_execution(route_state, monkeypatch):
    _, audit, tasks, _ = route_state
    task = TaskRecord(
        id="task-1", organization_id="org-1", project_id="project-1",
        owner_id=identity_owner_key("https://identity.example/", "user-1"), goal="Add tests", plan="Inspect and test",
        status=TaskStatus.AWAITING_APPROVAL, version=3,
        created_at=datetime.now(timezone.utc),
    )
    tasks.tasks[task.id] = task
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-1/approve",
        json={"expected_version": 3},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["version"] == 4
    assert audit.events[0]["action"] == "nexus.task.approve"


def test_stale_approval_version_returns_conflict(route_state):
    _, _, tasks, _ = route_state
    task = TaskRecord(
        id="task-1", organization_id="org-1", project_id="project-1",
        owner_id=identity_owner_key("https://identity.example/", "user-1"), goal="Add tests", plan="Inspect and test",
        status=TaskStatus.AWAITING_APPROVAL, version=3,
    )
    tasks.tasks[task.id] = task
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-1/approve",
        json={"expected_version": 2},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "TASK_VERSION_OR_STATE_CONFLICT"

  
def test_project_member_cannot_approve_another_users_task(route_state):
    database, audit, tasks, _ = route_state
    database.collections["projects"].document = {
        "organization_id": "org-1", "project_id": "project-1",
        "status": "active", "owner_issuer": "https://identity.example/",
        "owner_subject": "project-owner",
    }
    database.collections["project_memberships"].document = {"status": "active"}
    task = TaskRecord(
        id="task-2", organization_id="org-1", project_id="project-1",
        owner_id=identity_owner_key("https://identity.example/", "user-1"), goal="Add tests", plan="Inspect and test",
        status=TaskStatus.AWAITING_APPROVAL, version=3,
    )
    tasks.tasks[task.id] = task
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-2/approve",
        json={"expected_version": 3},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PROJECT_OWNER_APPROVAL_REQUIRED"
    assert tasks.tasks[task.id].status is TaskStatus.AWAITING_APPROVAL
    assert audit.events[-1]["action"] == "nexus.task.approve"
    assert audit.events[-1]["outcome"] == "denied"
    assert audit.events[-1]["metadata"]["reason"] == "project_owner_approval_required"


def test_same_subject_from_different_issuer_cannot_read_task(route_state):
    database, audit, tasks, _ = route_state
    database.collections["projects"].document = {
        "organization_id": "org-1", "project_id": "project-1",
        "status": "active", "owner_issuer": "https://identity.example/",
        "owner_subject": "project-owner",
    }
    database.collections["project_memberships"].document = {"status": "active"}
    task = TaskRecord(
        id="task-cross-issuer", organization_id="org-1", project_id="project-1",
        owner_id=identity_owner_key("https://issuer-a.example/", "same-subject"),
        goal="Private task", status=TaskStatus.AWAITING_APPROVAL, version=3,
        plan="Inspect and test",
    )
    tasks.tasks[task.id] = task
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="same-subject", issuer="https://issuer-b.example/",
    )
    response = TestClient(app).get(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-cross-issuer"
    )
    assert response.status_code == 404
    assert audit.events[-1]["action"] == "nexus.task.read"
    assert audit.events[-1]["outcome"] == "denied"
    assert audit.events[-1]["metadata"]["reason"] == "task_owner_required"


def test_task_read_success_is_audited(route_state):
    _, audit, tasks, _ = route_state
    task = TaskRecord(
        id="task-read", organization_id="org-1", project_id="project-1",
        owner_id=identity_owner_key("https://identity.example/", "user-1"),
        goal="Read task", plan="Plan", status=TaskStatus.AWAITING_APPROVAL, version=3,
    )
    tasks.tasks[task.id] = task
    response = TestClient(app).get(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-read"
    )
    assert response.status_code == 200
    assert audit.events[-1]["action"] == "nexus.task.read"
    assert audit.events[-1]["outcome"] == "success"
    assert audit.events[-1]["metadata"] == {"status": "awaiting_approval"}


def test_task_events_are_project_authorized_and_cursor_paginated(route_state):
    _, audit, tasks, _ = route_state
    task = TaskRecord(
        id="task-1", organization_id="org-1", project_id="project-1",
        owner_id=identity_owner_key("https://identity.example/", "user-1"),
        goal="Task events", plan="Plan", status=TaskStatus.AWAITING_APPROVAL, version=3,
    )
    tasks.tasks[task.id] = task
    response = TestClient(app).get(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-1/events",
        params={"after_version": 1, "limit": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert [event["version"] for event in body["events"]] == [2, 3]
    assert body["next_after_version"] == 3
    assert body["has_more"] is False
    assert audit.events[-1]["action"] == "nexus.task.events.read"
    assert audit.events[-1]["outcome"] == "success"
    assert audit.events[-1]["metadata"]["returned_count"] == 2


def test_project_nexus_chat_requires_explicit_cloud_consent(route_state):
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/chat",
        json={
            "messages": [{"role": "user", "content": "Review this project"}],
            "cloud_model_consent": False,
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "CLOUD_MODEL_CONSENT_REQUIRED"


def test_project_nexus_chat_is_authorized_read_only_and_audited(route_state, monkeypatch):
    _, audit, _, _ = route_state

    class Responses:
        def create(self, **kwargs):
            assert kwargs["store"] is False
            assert "tools" not in kwargs
            return SimpleNamespace(output_text="I reviewed the selected source.")

    monkeypatch.setattr(
        "odei_api.services.nexus_tasks.get_openai_client",
        lambda: (SimpleNamespace(responses=Responses()), "test-model"),
    )
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/chat",
        json={
            "messages": [{"role": "user", "content": "Review this project"}],
            "workspace_files": [{"path": "src/main.py", "content": "print('hello')"}],
            "cloud_model_consent": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "answer": "I reviewed the selected source.",
        "model": "test-model",
        "read_only": True,
        "tools_executed": 0,
        "conversation_persisted": False,
    }
    assert [event["outcome"] for event in audit.events] == ["started", "success"]
    assert all("Review this project" not in str(event) for event in audit.events)
    assert audit.events[-1]["action"] == "nexus.chat.request"
    assert audit.events[-1]["metadata"]["workspace_file_count"] == 1


def test_project_nexus_chat_requires_authorized_project(route_state):
    database, audit, _, _ = route_state
    database.collections["projects"].document = None
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/chat",
        json={
            "messages": [{"role": "user", "content": "Review this project"}],
            "cloud_model_consent": True,
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
    assert audit.events[-1]["action"] == "nexus.project.access"
    assert audit.events[-1]["outcome"] == "denied"



def test_conversation_create_list_and_get_are_project_and_identity_scoped(route_state):
    _, audit, _, conversations = route_state
    client = TestClient(app)
    created = client.post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/conversations",
        json={"title": "Architecture discussion"},
    )
    assert created.status_code == 200, created.text
    conversation_id = created.json()["conversation_id"]
    listed = client.get(
        "/api/v1/organizations/org-1/projects/project-1/nexus/conversations"
    )
    assert listed.status_code == 200
    assert len(listed.json()["conversations"]) == 1
    assert "messages" not in listed.json()["conversations"][0]
    loaded = client.get(
        f"/api/v1/organizations/org-1/projects/project-1/nexus/conversations/{conversation_id}"
    )
    assert loaded.status_code == 200
    assert loaded.json()["title"] == "Architecture discussion"
    assert [event["action"] for event in audit.events] == [
        "nexus.conversation.create", "nexus.conversation.list", "nexus.conversation.read",
    ]
    assert len(conversations.documents) == 1


def test_conversation_history_cannot_be_read_by_another_identity(route_state):
    _, audit, _, _ = route_state
    client = TestClient(app)
    created = client.post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/conversations",
        json={"title": "Private conversation"},
    ).json()
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="other-user", issuer="https://identity.example/",
    )
    response = client.get(
        f"/api/v1/organizations/org-1/projects/project-1/nexus/conversations/{created['conversation_id']}"
    )
    assert response.status_code == 404
    assert audit.events[-1]["outcome"] == "denied"


def test_nexus_chat_persists_user_and_assistant_turns_in_conversation(route_state, monkeypatch):
    _, _, _, conversations = route_state
    item = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/conversations",
        json={"title": "Persistent chat"},
    ).json()

    class Responses:
        def create(self, **kwargs):
            assert kwargs["store"] is False
            assert kwargs["input"][-1]["content"] == "Remember this conversation"
            return SimpleNamespace(output_text="I will use the saved context.")

    monkeypatch.setattr(
        "odei_api.services.nexus_tasks.get_openai_client",
        lambda: (SimpleNamespace(responses=Responses()), "test-model"),
    )
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/chat",
        json={
            "messages": [{"role": "user", "content": "Remember this conversation"}],
            "conversation_id": item["conversation_id"],
            "cloud_model_consent": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["conversation_persisted"] is True
    assert response.json()["conversation_id"] == item["conversation_id"]
    stored = conversations.documents[item["conversation_id"]]
    assert [message["role"] for message in stored["messages"]] == ["user", "assistant"]
    assert stored["messages"][1]["content"] == "I will use the saved context."



def test_conversation_message_append_and_delete_are_audited(route_state):
    _, audit, _, conversations = route_state
    client = TestClient(app)
    item = client.post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/conversations",
        json={"title": "Message lifecycle"},
    ).json()
    conversation_id = item["conversation_id"]
    appended = client.post(
        f"/api/v1/organizations/org-1/projects/project-1/nexus/conversations/{conversation_id}/messages",
        json={"role": "user", "content": "Hello", "expected_version": 0},
    )
    assert appended.status_code == 200, appended.text
    assert appended.json()["version"] == 1
    assert appended.json()["messages"][0]["content"] == "Hello"
    deleted = client.delete(
        f"/api/v1/organizations/org-1/projects/project-1/nexus/conversations/{conversation_id}"
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert conversation_id not in conversations.documents
    assert audit.events[-2]["action"] == "nexus.conversation.message.append"
    assert audit.events[-1]["action"] == "nexus.conversation.delete"

def test_nexus_stream_endpoint_persists_and_emits_redacted_sse_deltas(route_state, monkeypatch):
    _, audit, _, conversations = route_state
    item = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/conversations",
        json={"title": "Streaming conversation"},
    ).json()

    class Stream:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def __iter__(self):
            return iter([
                SimpleNamespace(type="response.output_text.delta", delta="Hello "),
                SimpleNamespace(type="response.output_text.delta", delta="api_key=super_secret_token_12345"),
                SimpleNamespace(type="response.output_text.delta", delta=" and welcome."),
                SimpleNamespace(type="response.completed"),
            ])

    class Responses:
        def stream(self, **kwargs):
            assert kwargs["store"] is False
            assert "tools" not in kwargs
            return Stream()

    monkeypatch.setattr(
        "odei_api.services.nexus_tasks.get_openai_client",
        lambda: (SimpleNamespace(responses=Responses()), "stream-model"),
    )
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/chat/stream",
        json={
            "messages": [{"role": "user", "content": "Say hello"}],
            "conversation_id": item["conversation_id"],
            "cloud_model_consent": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: delta" in response.text
    assert "event: done" in response.text
    assert "super_secret_token_12345" not in response.text
    saved = conversations.documents[item["conversation_id"]]
    assert [message["role"] for message in saved["messages"]] == ["user", "assistant"]
    assert "[REDACTED]" in saved["messages"][-1]["content"]
    assert audit.events[-1]["outcome"] == "success"


def test_nexus_inspection_uses_only_attached_excerpt_tools_and_persists_result(route_state, monkeypatch):
    _, audit, _, conversations = route_state
    client = TestClient(app)
    item = client.post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/conversations",
        json={"title": "Attached file inspection"},
    ).json()
    secret = "sk-proj-" + "A" * 28

    def fake_agent(_client, *, model, task, workspace_tools, cloud_model_consent, prior_messages):
        assert model == "inspection-model"
        assert task == "Explain this selected file"
        assert cloud_model_consent is True
        assert prior_messages == []
        listed = workspace_tools.execute("list_attached_excerpts", {})
        assert "src/main.py" in listed
        read = workspace_tools.execute("read_attached_excerpt", {"path": "src/main.py"})
        assert "def hello" in read
        assert secret not in read
        return SimpleNamespace(
            answer="The attached file defines hello().",
            model=model,
            tool_calls=2,
            tool_rounds=2,
            tool_names=("list_attached_excerpts", "read_attached_excerpt"),
        )

    monkeypatch.setattr(
        "odei_api.services.nexus_inspection.get_openai_client",
        lambda: (object(), "inspection-model"),
    )
    monkeypatch.setattr("odei_api.services.nexus_inspection.run_nexus_agent", fake_agent)
    response = client.post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/chat/inspect",
        json={
            "messages": [{"role": "user", "content": "Explain this selected file"}],
            "workspace_files": [{"path": "src/main.py", "content": "def hello(): return 'ODEI'\\napi_key=" + secret}],
            "conversation_id": item["conversation_id"],
            "cloud_model_consent": True,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tools_executed"] == 2
    assert body["tool_names"] == ["list_attached_excerpts", "read_attached_excerpt"]
    assert body["conversation_persisted"] is True
    stored = conversations.documents[item["conversation_id"]]
    assert [message["role"] for message in stored["messages"]] == ["user", "assistant"]
    assert stored["messages"][-1]["content"] == "The attached file defines hello()."
    assert audit.events[-1]["metadata"]["tool_call_count"] == 2


def test_nexus_inspection_persists_model_generated_patch_for_owner_review(route_state, monkeypatch):
    _, audit, _, _conversations = route_state
    client = TestClient(app)
    item = client.post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/conversations",
        json={"title": "Generate a patch"},
    ).json()
    original = "def greet(): return 'hello'"
    replacement = "def greet(): return 'hello from ODEI'"

    def fake_agent(_client, *, model, task, workspace_tools, cloud_model_consent, prior_messages):
        assert cloud_model_consent is True
        assert workspace_tools.proposal_base_files == {}
        workspace_tools.execute("propose_attached_file_change", {
            "path": "src/greet.py", "content": replacement,
        })
        return SimpleNamespace(
            answer="I prepared a review-only patch proposal.",
            model=model, tool_calls=1, tool_rounds=1,
            tool_names=("propose_attached_file_change",),
        )

    monkeypatch.setattr(
        "odei_api.services.nexus_inspection.get_openai_client",
        lambda: (object(), "proposal-model"),
    )
    monkeypatch.setattr("odei_api.services.nexus_inspection.run_nexus_agent", fake_agent)
    response = client.post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/chat/inspect",
        json={
            "messages": [{"role": "user", "content": "Change greet"}],
            "workspace_files": [{"path": "src/greet.py", "content": original}],
            "conversation_id": item["conversation_id"],
            "cloud_model_consent": True,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["patch_proposal"]["status"] == "pending"
    assert body["patch_proposal"]["application_enabled"] is False
    assert body["patch_proposal"]["can_decide"] is True
    stored = app.state.patch_proposal_store.documents[body["patch_proposal"]["proposal_id"]]
    assert stored["files"][0]["content"] == replacement
    assert stored["files"][0]["base_sha256"]
    assert "hello from ODEI" in stored["files"][0]["unified_diff"]
    proposal_events = [event for event in audit.events if event["action"] == "nexus.patch_proposal.create"]
    assert [event["outcome"] for event in proposal_events] == ["started", "success"]
    assert all("prompt" not in event["metadata"] and "source" not in event["metadata"] for event in proposal_events)


def test_nexus_inspection_rejects_unattached_or_unsafe_paths_before_model_call(route_state, monkeypatch):
    _, _, _, conversations = route_state
    item = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/conversations",
        json={"title": "Unsafe attachment"},
    ).json()
    called = []
    monkeypatch.setattr(
        "odei_api.services.nexus_inspection.get_openai_client",
        lambda: called.append(True),
    )
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/chat/inspect",
        json={
            "messages": [{"role": "user", "content": "Read outside"}],
            "workspace_files": [{"path": "../outside.txt", "content": "secret"}],
            "conversation_id": item["conversation_id"],
            "cloud_model_consent": True,
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_ATTACHED_EXCERPT"
    assert called == []
    assert conversations.documents[item["conversation_id"]]["messages"] == []
