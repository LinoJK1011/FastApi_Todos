from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import Optional, List
from pathlib import Path
import json
from datetime import datetime, timezone

app = FastAPI()

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
def get_todos_by_group(group_id: int):
    if group_id < 1 or group_id > 9:
        raise HTTPException(status_code=400, detail="Group ID must be between 1 and 9")
    todos = load_todos()
    filtered = [todo for todo in todos if todo.get("group") == group_id]
    return filtered

# Read - 완료/미완료 상태별 필터링
@app.get("/todos/status/{status}", response_model=List[TodoItem])
def get_todos_by_status(status: str):
    todos = load_todos()
    if status == "completed":
        return [todo for todo in todos if todo.get("completed")]
    elif status == "pending":
        return [todo for todo in todos if not todo.get("completed")]
    else:
        raise HTTPException(status_code=400, detail="Status must be 'completed' or 'pending'")

# Read - 정렬 기능
@app.get("/todos/sorted", response_model=List[TodoItem])
def get_sorted_todos(sort_by: str = "created_at", order: str = "desc"):
    """
    정렬 가능한 필드: id, title, created_at, completed, completed_at, group
    정렬 순서: asc (오름차순), desc (내림차순)
    """
    valid_sort_fields = ["id", "title", "created_at", "completed", "completed_at", "group"]
    if sort_by not in valid_sort_fields:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid sort_by field. Must be one of: {', '.join(valid_sort_fields)}"
        )
    if order not in ["asc", "desc"]:
        raise HTTPException(status_code=400, detail="Order must be 'asc' or 'desc'")
    
    todos = load_todos()
    reverse = (order == "desc")
    
    # None 값 처리를 위한 정렬
    def sort_key(todo):
        value = todo.get(sort_by)
        # None 값은 정렬 시 맨 뒤로 보냄
        if value is None:
            return ("", "") if not reverse else ("~", "~")
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

# Update
@app.put("/todos/{todo_id}", response_model=TodoItem)
def update_todo(todo_id: int, patch: TodoUpdate):
    todos = load_todos()
    for i, todo in enumerate(todos):
        if todo.get("id") == todo_id:
            # Apply updates
            if patch.title is not None:
                todo["title"] = patch.title
            if patch.description is not None:
                todo["description"] = patch.description
            if patch.group is not None:
                todo["group"] = patch.group

            if patch.completed is not None:
                prev = bool(todo.get("completed", False))
                todo["completed"] = bool(patch.completed)
                if todo["completed"] and not prev:
                    todo["completed_at"] = datetime.now(timezone.utc).isoformat()
                if not todo["completed"]:
                    todo["completed_at"] = None

            todos[i] = todo
            save_todos(todos)
            return TodoItem(**todo)
    raise HTTPException(status_code=404, detail="To-Do item not found")

# Delete
@app.delete("/todos/{todo_id}", response_model=dict)
def delete_todo(todo_id: int):
    todos = load_todos()
    new_todos = [todo for todo in todos if todo.get("id") != todo_id]
    if len(new_todos) == len(todos):
        raise HTTPException(status_code=404, detail="To-Do item not found")
    save_todos(new_todos)
    return {"message": "To-Do item deleted"}

#이거는 풋이랑 딜리트에서 먼저 읽을때 이용(개별항목)
@app.get("/todos/{todo_id}", response_model=TodoItem)
def get_todo(todo_id: int):
    todos = load_todos()
    for todo in todos:
        if todo.get("id") == todo_id:
            return TodoItem(**todo)
    raise HTTPException(status_code=404, detail="To-Do item not found")


@app.get("/", response_class=HTMLResponse)
def read_root():
    if not INDEX_FILE.exists():
        raise HTTPException(status_code=500, detail="index.html not found")
    with open(INDEX_FILE, "r", encoding="utf-8") as file:
        content = file.read()
    return HTMLResponse(content=content)


#요구사항에 따라 앱 로드시 빈 배열로 초기화
with open(TODO_FILE, "w", encoding="utf-8") as file:
    json.dump([], file, ensure_ascii=False, indent=4)
