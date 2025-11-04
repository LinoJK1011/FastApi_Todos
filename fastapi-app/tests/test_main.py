import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from fastapi.testclient import TestClient
from main import app, save_todos, load_todos, TodoItem
from datetime import datetime, timezone

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_and_teardown():
    # 테스트 전 초기화
    save_todos([])
    yield
    # 테스트 후 정리
    save_todos([])


# ============================================
# Helper Functions
# ============================================

def create_test_todo(id=1, title="Test", description="Test description",
                     completed=False, group=1, created_at=None, completed_at=None):
    """테스트용 TodoItem 생성"""
    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat()
    return TodoItem(
        id=id,
        title=title,
        description=description,
        created_at=created_at,
        completed=completed,
        completed_at=completed_at,
        group=group
    )


# ============================================
# Basic CRUD Tests
# ============================================

def test_get_todos_empty():
    """빈 배열 조회"""
    response = client.get("/todos")
    assert response.status_code == 200
    assert response.json() == []


def test_get_todos_with_items():
    """여러 항목 조회"""
    todo1 = create_test_todo(id=1, title="Test 1", group=1)
    todo2 = create_test_todo(id=2, title="Test 2", group=2)
    save_todos([todo1.model_dump(), todo2.model_dump()])

    response = client.get("/todos")
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.json()[0]["title"] == "Test 1"
    assert response.json()[1]["title"] == "Test 2"


def test_create_todo_basic():
    """기본 todo 생성"""
    todo_data = {"title": "New Task", "description": "Task description"}
    response = client.post("/todos", json=todo_data)

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "New Task"
    assert data["description"] == "Task description"
    assert data["id"] == 1
    assert data["completed"] is False
    assert data["completed_at"] is None
    assert data["group"] == 1  # 기본값
    assert "created_at" in data


def test_create_todo_with_group():
    """그룹 지정하여 todo 생성"""
    todo_data = {"title": "Task", "description": "Desc", "group": 5}
    response = client.post("/todos", json=todo_data)

    assert response.status_code == 200
    assert response.json()["group"] == 5


def test_create_todo_auto_id():
    """id 자동 증가 확인"""
    response1 = client.post("/todos", json={"title": "Task 1"})
    response2 = client.post("/todos", json={"title": "Task 2"})

    assert response1.json()["id"] == 1
    assert response2.json()["id"] == 2


def test_create_todo_invalid_group():
    """잘못된 group 값 (범위 초과)"""
    # group > 9
    response = client.post("/todos", json={"title": "Task", "group": 10})
    assert response.status_code == 422

    # group < 1
    response = client.post("/todos", json={"title": "Task", "group": 0})
    assert response.status_code == 422


def test_create_todo_missing_title():
    """필수 필드 누락"""
    response = client.post("/todos", json={"description": "No title"})
    assert response.status_code == 422


def test_get_single_todo():
    """개별 todo 조회"""
    todo = create_test_todo(id=1, title="Single Task")
    save_todos([todo.model_dump()])

    response = client.get("/todos/1")
    assert response.status_code == 200
    assert response.json()["title"] == "Single Task"


def test_get_single_todo_not_found():
    """존재하지 않는 todo 조회"""
    response = client.get("/todos/999")
    assert response.status_code == 404


def test_update_todo_title_description():
    """제목과 설명 수정"""
    todo = create_test_todo(id=1, title="Original", description="Original desc")
    save_todos([todo.model_dump()])

    update_data = {"title": "Updated", "description": "Updated desc"}
    response = client.put("/todos/1", json=update_data)

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated"
    assert data["description"] == "Updated desc"


def test_update_todo_marks_completed():
    """완료 처리 시 completed_at 자동 설정"""
    todo = create_test_todo(id=1, completed=False)
    save_todos([todo.model_dump()])

    response = client.put("/todos/1", json={"completed": True})

    assert response.status_code == 200
    data = response.json()
    assert data["completed"] is True
    assert data["completed_at"] is not None


def test_update_todo_unmarks_completed():
    """완료 취소 시 completed_at null"""
    todo = create_test_todo(id=1, completed=True,
                           completed_at=datetime.now(timezone.utc).isoformat())
    save_todos([todo.model_dump()])

    response = client.put("/todos/1", json={"completed": False})

    assert response.status_code == 200
    data = response.json()
    assert data["completed"] is False
    assert data["completed_at"] is None


def test_update_todo_change_group():
    """그룹 변경"""
    todo = create_test_todo(id=1, group=1)
    save_todos([todo.model_dump()])

    response = client.put("/todos/1", json={"group": 3})

    assert response.status_code == 200
    assert response.json()["group"] == 3


def test_update_todo_not_found():
    """존재하지 않는 todo 수정"""
    response = client.put("/todos/999", json={"title": "Updated"})
    assert response.status_code == 404


def test_delete_todo():
    """todo 삭제"""
    todo = create_test_todo(id=1)
    save_todos([todo.model_dump()])

    response = client.delete("/todos/1")
    assert response.status_code == 200
    assert response.json()["message"] == "To-Do item deleted"

    # 삭제 확인
    todos = load_todos()
    assert len(todos) == 0


def test_delete_todo_not_found():
    """존재하지 않는 todo 삭제"""
    response = client.delete("/todos/999")
    assert response.status_code == 404


# ============================================
# Group Filtering Tests
# ============================================

def test_get_todos_by_group():
    """특정 그룹의 todo 조회"""
    todo1 = create_test_todo(id=1, title="Group 1 Task", group=1)
    todo2 = create_test_todo(id=2, title="Group 2 Task", group=2)
    todo3 = create_test_todo(id=3, title="Group 1 Another", group=1)
    save_todos([todo1.model_dump(), todo2.model_dump(), todo3.model_dump()])

    response = client.get("/todos/group/1")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(item["group"] == 1 for item in data)


def test_get_todos_by_group_empty():
    """해당 그룹에 todo가 없는 경우"""
    todo = create_test_todo(id=1, group=1)
    save_todos([todo.model_dump()])

    response = client.get("/todos/group/5")
    assert response.status_code == 200
    assert response.json() == []


def test_get_todos_by_group_invalid_id():
    """잘못된 group_id"""
    # group_id < 1
    response = client.get("/todos/group/0")
    assert response.status_code == 400

    # group_id > 9
    response = client.get("/todos/group/10")
    assert response.status_code == 400


# ============================================
# Status Filtering Tests
# ============================================

def test_get_todos_by_status_completed():
    """완료된 todo만 조회"""
    todo1 = create_test_todo(id=1, title="Done", completed=True)
    todo2 = create_test_todo(id=2, title="Pending", completed=False)
    todo3 = create_test_todo(id=3, title="Also Done", completed=True)
    save_todos([todo1.model_dump(), todo2.model_dump(), todo3.model_dump()])

    response = client.get("/todos/status/completed")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(item["completed"] is True for item in data)


def test_get_todos_by_status_pending():
    """미완료 todo만 조회"""
    todo1 = create_test_todo(id=1, title="Done", completed=True)
    todo2 = create_test_todo(id=2, title="Pending", completed=False)
    todo3 = create_test_todo(id=3, title="Also Pending", completed=False)
    save_todos([todo1.model_dump(), todo2.model_dump(), todo3.model_dump()])

    response = client.get("/todos/status/pending")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(item["completed"] is False for item in data)


def test_get_todos_by_status_invalid():
    """잘못된 status 값"""
    response = client.get("/todos/status/invalid")
    assert response.status_code == 400


# ============================================
# Sorting Tests
# ============================================

def test_sorted_todos_default():
    """기본 정렬 (created_at desc)"""
    import time

    todo1 = create_test_todo(id=1, title="First", created_at="2024-01-01T00:00:00Z")
    time.sleep(0.01)
    todo2 = create_test_todo(id=2, title="Second", created_at="2024-01-02T00:00:00Z")
    time.sleep(0.01)
    todo3 = create_test_todo(id=3, title="Third", created_at="2024-01-03T00:00:00Z")
    save_todos([todo1.model_dump(), todo2.model_dump(), todo3.model_dump()])

    response = client.get("/todos/sorted")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["title"] == "Third"  # 최신
    assert data[2]["title"] == "First"   # 가장 오래된


def test_sorted_todos_by_title_asc():
    """제목 오름차순 정렬"""
    todo1 = create_test_todo(id=1, title="Charlie")
    todo2 = create_test_todo(id=2, title="Alice")
    todo3 = create_test_todo(id=3, title="Bob")
    save_todos([todo1.model_dump(), todo2.model_dump(), todo3.model_dump()])

    response = client.get("/todos/sorted?sort_by=title&order=asc")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["title"] == "Alice"
    assert data[1]["title"] == "Bob"
    assert data[2]["title"] == "Charlie"


def test_sorted_todos_by_group():
    """그룹별 정렬"""
    todo1 = create_test_todo(id=1, title="Task", group=3)
    todo2 = create_test_todo(id=2, title="Task", group=1)
    todo3 = create_test_todo(id=3, title="Task", group=2)
    save_todos([todo1.model_dump(), todo2.model_dump(), todo3.model_dump()])

    response = client.get("/todos/sorted?sort_by=group&order=asc")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["group"] == 1
    assert data[1]["group"] == 2
    assert data[2]["group"] == 3


def test_sorted_todos_completed_at_with_none():
    """completed_at이 None인 항목 포함 정렬"""
    todo1 = create_test_todo(id=1, completed=True, completed_at="2024-01-01T00:00:00Z")
    todo2 = create_test_todo(id=2, completed=False, completed_at=None)
    todo3 = create_test_todo(id=3, completed=True, completed_at="2024-01-02T00:00:00Z")
    save_todos([todo1.model_dump(), todo2.model_dump(), todo3.model_dump()])

    response = client.get("/todos/sorted?sort_by=completed_at&order=desc")
    assert response.status_code == 200
    # None 값이 있어도 에러 없이 정렬됨
    assert len(response.json()) == 3


def test_sorted_todos_invalid_sort_by():
    """잘못된 sort_by 필드"""
    response = client.get("/todos/sorted?sort_by=invalid_field")
    assert response.status_code == 400


def test_sorted_todos_invalid_order():
    """잘못된 order 값"""
    response = client.get("/todos/sorted?sort_by=title&order=invalid")
    assert response.status_code == 400


# ============================================
# Integration Tests
# ============================================

def test_full_workflow():
    """전체 플로우: 생성 → 조회 → 수정 → 삭제"""
    # 1. 생성
    create_response = client.post("/todos", json={
        "title": "Workflow Test",
        "description": "Full test",
        "group": 2
    })
    assert create_response.status_code == 200
    todo_id = create_response.json()["id"]

    # 2. 조회
    get_response = client.get(f"/todos/{todo_id}")
    assert get_response.status_code == 200
    assert get_response.json()["title"] == "Workflow Test"

    # 3. 수정
    update_response = client.put(f"/todos/{todo_id}", json={
        "title": "Updated Workflow",
        "completed": True
    })
    assert update_response.status_code == 200
    assert update_response.json()["completed"] is True

    # 4. 삭제
    delete_response = client.delete(f"/todos/{todo_id}")
    assert delete_response.status_code == 200

    # 5. 삭제 확인
    final_get = client.get(f"/todos/{todo_id}")
    assert final_get.status_code == 404


def test_multiple_groups_filtering():
    """여러 그룹 생성 후 필터링"""
    # 각 그룹에 todo 생성
    for group in [1, 2, 3]:
        for i in range(2):
            client.post("/todos", json={
                "title": f"Group {group} Task {i+1}",
                "group": group
            })

    # 전체 조회
    all_response = client.get("/todos")
    assert len(all_response.json()) == 6

    # 그룹별 조회
    group2_response = client.get("/todos/group/2")
    assert len(group2_response.json()) == 2
    assert all(item["group"] == 2 for item in group2_response.json())


def test_status_filtering_after_completion():
    """완료 처리 후 상태별 조회"""
    # 3개 todo 생성
    for i in range(3):
        client.post("/todos", json={"title": f"Task {i+1}"})

    # 첫 번째 완료 처리
    client.put("/todos/1", json={"completed": True})

    # 상태별 조회
    completed = client.get("/todos/status/completed")
    pending = client.get("/todos/status/pending")

    assert len(completed.json()) == 1
    assert len(pending.json()) == 2
