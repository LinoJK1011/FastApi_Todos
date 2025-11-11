from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from pathlib import Path
import json
from datetime import datetime, timezone
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()

# Prometheus 메트릭스 엔드포인트 (/metrics)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# i18n Support
MULTILANG_DIR = Path(__file__).resolve().parent / "multilang"
_i18n_cache: Dict[str, Dict[str, Any]] = {}

def load_i18n(lang: str = "ko") -> Dict[str, Any]:
    """Load language file from multilang directory"""
    if lang not in _i18n_cache:
        lang_file = MULTILANG_DIR / f"{lang}.json"
        if not lang_file.exists():
            lang = "ko"  # fallback to Korean
            lang_file = MULTILANG_DIR / f"{lang}.json"

        with open(lang_file, "r", encoding="utf-8") as f:
            _i18n_cache[lang] = json.load(f)

    return _i18n_cache[lang]

def get_lang(request: Request) -> str:
    """Get language from Accept-Language header or default to Korean"""
    accept_lang = request.headers.get("Accept-Language", "ko")
    # Simple language detection: ko, en
    if "en" in accept_lang.lower():
        return "en"
    return "ko"

def t(request: Request, key_path: str) -> str:
    """Translate function - get message by dot-notation key path"""
    lang = get_lang(request)
    messages = load_i18n(lang)

    keys = key_path.split(".")
    value = messages
    for key in keys:
        value = value.get(key, key_path)
        if not isinstance(value, dict):
            break

    return value if isinstance(value, str) else key_path

# i18n message keys (constants to avoid string literal duplication)
TODO_NOT_FOUND = "api.todo_not_found"
TODO_DELETED = "api.todo_deleted"

class TodoItem(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    created_at: str
    completed: bool = False
    completed_at: Optional[str] = None
    group: int = Field(default=1, ge=1, le=9)


class TodoCreate(BaseModel):
    title: str
    description: Optional[str] = None
    group: int = Field(default=1, ge=1, le=9)


class TodoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    completed: Optional[bool] = None
    group: Optional[int] = Field(default=None, ge=1, le=9)


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
INDEX_FILE = TEMPLATES_DIR / "index.html"


TODO_FILE = BASE_DIR / "todo.json"


def load_todos() -> List[dict]:
    if TODO_FILE.exists():
        try:
            with open(TODO_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)
                if isinstance(data, list):
                    return data
        except json.JSONDecodeError:
            pass
    return []


def save_todos(todos: List[dict]) -> None:
    with open(TODO_FILE, "w", encoding="utf-8") as file:
        json.dump(todos, file, ensure_ascii=False, indent=4)


def next_id(todos: List[dict]) -> int:
    return (max((t["id"] for t in todos), default=0) + 1) if todos else 1

# Read
@app.get("/todos", response_model=List[TodoItem])
def get_todos():
    return load_todos()

# Read - 그룹별 필터링
@app.get("/todos/group/{group_id}", response_model=List[TodoItem])
def get_todos_by_group(group_id: int, request: Request):
    if group_id < 1 or group_id > 9:
        raise HTTPException(status_code=400, detail=t(request, "api.group_id_invalid"))
    todos = load_todos()
    filtered = [todo for todo in todos if todo.get("group") == group_id]
    return filtered

# Read - 완료/미완료 상태별 필터링
@app.get("/todos/status/{status}", response_model=List[TodoItem])
def get_todos_by_status(status: str, request: Request):
    todos = load_todos()
    if status == "completed":
        return [todo for todo in todos if todo.get("completed")]
    elif status == "pending":
        return [todo for todo in todos if not todo.get("completed")]
    else:
        raise HTTPException(status_code=400, detail=t(request, "api.status_invalid"))

# Read - 정렬 기능
@app.get("/todos/sorted", response_model=List[TodoItem])
def get_sorted_todos(sort_by: str = "created_at", order: str = "desc", request: Request = None):
    """
    정렬 가능한 필드: id, title, created_at, completed, completed_at, group
    정렬 순서: asc (오름차순), desc (내림차순)
    """
    valid_sort_fields = ["id", "title", "created_at", "completed", "completed_at", "group"]
    if sort_by not in valid_sort_fields:
        raise HTTPException(
            status_code=400,
            detail=f"{t(request, 'api.sort_field_invalid')} {', '.join(valid_sort_fields)}"
        )
    if order not in ["asc", "desc"]:
        raise HTTPException(status_code=400, detail=t(request, "api.order_invalid"))
    
    todos = load_todos()
    reverse = (order == "desc")
    
    # None 값 처리를 위한 정렬
    def sort_key(todo):
        value = todo.get(sort_by)
        # None 값 처리: 타입 일관성 유지
        if value is None:
            # 오름차순: None을 맨 앞으로, 내림차순: None을 맨 뒤로
            return "" if not reverse else "\uffff"
        return value
    
    sorted_todos = sorted(todos, key=sort_key, reverse=reverse)
    return sorted_todos

# Create
@app.post("/todos", response_model=TodoItem)
def create_todo(todo: TodoCreate):
    todos = load_todos()
    now = datetime.now(timezone.utc).isoformat()
    item = TodoItem(
        id=next_id(todos),
        title=todo.title,
        description=todo.description,
        created_at=now,
        completed=False,
        completed_at=None,
        group=todo.group or 1,
    )
    todos.append(item.model_dump())
    save_todos(todos)
    return item

# Helper functions for update_todo
def _apply_simple_fields(todo: dict, patch: TodoUpdate) -> None:
    """Apply simple field updates (title, description, group) from patch to todo"""
    simple_fields = ["title", "description", "group"]
    for field in simple_fields:
        value = getattr(patch, field, None)
        if value is not None:
            todo[field] = value


def _update_completed_status(todo: dict, new_completed: bool) -> None:
    """Update completed status and manage completed_at timestamp"""
    prev_completed = bool(todo.get("completed", False))
    todo["completed"] = bool(new_completed)

    # Set completed_at when transitioning from incomplete to complete
    if todo["completed"] and not prev_completed:
        todo["completed_at"] = datetime.now(timezone.utc).isoformat()
    # Clear completed_at when marking as incomplete
    elif not todo["completed"]:
        todo["completed_at"] = None


# Update
@app.put("/todos/{todo_id}", response_model=TodoItem)
def update_todo(todo_id: int, patch: TodoUpdate, request: Request):
    todos = load_todos()
    for i, todo in enumerate(todos):
        if todo.get("id") == todo_id:
            # Apply simple field updates
            _apply_simple_fields(todo, patch)

            # Handle completed status updates
            if patch.completed is not None:
                _update_completed_status(todo, patch.completed)

            todos[i] = todo
            save_todos(todos)
            return TodoItem(**todo)
    raise HTTPException(status_code=404, detail=t(request, TODO_NOT_FOUND))

# Delete
@app.delete("/todos/{todo_id}", response_model=dict)
def delete_todo(todo_id: int, request: Request):
    todos = load_todos()
    new_todos = [todo for todo in todos if todo.get("id") != todo_id]
    if len(new_todos) == len(todos):
        raise HTTPException(status_code=404, detail=t(request, TODO_NOT_FOUND))
    save_todos(new_todos)
    return {"message": t(request, TODO_DELETED)}

#이거는 풋이랑 딜리트에서 먼저 읽을때 이용(개별항목)
@app.get("/todos/{todo_id}", response_model=TodoItem)
def get_todo(todo_id: int, request: Request):
    todos = load_todos()
    for todo in todos:
        if todo.get("id") == todo_id:
            return TodoItem(**todo)
    raise HTTPException(status_code=404, detail=t(request, TODO_NOT_FOUND))


@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    if not INDEX_FILE.exists():
        raise HTTPException(status_code=500, detail=t(request, "api.index_not_found"))
    with open(INDEX_FILE, "r", encoding="utf-8") as file:
        content = file.read()
    return HTMLResponse(content=content)


# i18n API - Get language file for frontend
@app.get("/i18n/{lang}")
def get_i18n(lang: str):
    """Return language file for frontend i18n"""
    try:
        messages = load_i18n(lang)
        return messages
    except Exception:
        # Fallback to Korean
        return load_i18n("ko")


#요구사항에 따라 앱 로드시 빈 배열로 초기화
with open(TODO_FILE, "w", encoding="utf-8") as file:
    json.dump([], file, ensure_ascii=False, indent=4)
