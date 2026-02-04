# Repo Removal Feature Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add ability to remove repositories from the picker with full cleanup of indexed data and cloned repos.

**Architecture:** Extend `RepoIngester` to store/retrieve source URLs and delete cloned repos. Add `ProjectInfo` dataclass and `get_project_info()` to `Shesha`. Enhance `delete_project()` with `cleanup_repo` parameter. Update `repo.py` picker with deletion support.

**Tech Stack:** Python, pytest, dataclasses

---

### Task 1: Store source URL in repo metadata

**Files:**
- Modify: `src/shesha/repo/ingester.py:101-106`
- Test: `tests/unit/repo/test_ingester.py`

**Step 1: Write the failing test**

```python
# In tests/unit/repo/test_ingester.py, add to existing test class:

def test_save_source_url_stores_url(self, tmp_path: Path):
    """save_source_url stores the original source URL in metadata."""
    ingester = RepoIngester(tmp_path)

    ingester.save_source_url("my-project", "https://github.com/org/repo")

    assert ingester.get_source_url("my-project") == "https://github.com/org/repo"


def test_save_source_url_stores_local_path(self, tmp_path: Path):
    """save_source_url stores local paths correctly."""
    ingester = RepoIngester(tmp_path)

    ingester.save_source_url("local-project", "/path/to/local/repo")

    assert ingester.get_source_url("local-project") == "/path/to/local/repo"


def test_get_source_url_returns_none_when_not_set(self, tmp_path: Path):
    """get_source_url returns None when no URL has been saved."""
    ingester = RepoIngester(tmp_path)

    assert ingester.get_source_url("nonexistent") is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/repo/test_ingester.py -v -k "source_url"`
Expected: FAIL with "AttributeError: 'RepoIngester' object has no attribute 'save_source_url'"

**Step 3: Write minimal implementation**

In `src/shesha/repo/ingester.py`, add two new methods after `save_sha`:

```python
def save_source_url(self, project_id: str, url: str) -> None:
    """Save the source URL for a project."""
    repo_path = self.repos_dir / project_id
    repo_path.mkdir(parents=True, exist_ok=True)
    meta_path = repo_path / "_repo_meta.json"

    # Load existing metadata or start fresh
    if meta_path.exists():
        data = json.loads(meta_path.read_text())
    else:
        data = {}

    data["source_url"] = url
    meta_path.write_text(json.dumps(data))

def get_source_url(self, project_id: str) -> str | None:
    """Get the saved source URL for a project."""
    meta_path = self.repos_dir / project_id / "_repo_meta.json"
    if not meta_path.exists():
        return None
    data = json.loads(meta_path.read_text())
    url = data.get("source_url")
    return str(url) if url is not None else None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/repo/test_ingester.py -v -k "source_url"`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/repo/ingester.py tests/unit/repo/test_ingester.py
git commit -m "feat(repo): add save_source_url and get_source_url methods"
```

---

### Task 2: Add delete_repo method to RepoIngester

**Files:**
- Modify: `src/shesha/repo/ingester.py`
- Test: `tests/unit/repo/test_ingester.py`

**Step 1: Write the failing test**

```python
def test_delete_repo_removes_cloned_directory(self, tmp_path: Path):
    """delete_repo removes the cloned repository directory."""
    ingester = RepoIngester(tmp_path)
    repo_path = ingester.repos_dir / "my-project"
    repo_path.mkdir(parents=True)
    (repo_path / "file.txt").write_text("content")

    ingester.delete_repo("my-project")

    assert not repo_path.exists()


def test_delete_repo_does_nothing_for_nonexistent(self, tmp_path: Path):
    """delete_repo silently succeeds for non-existent repos."""
    ingester = RepoIngester(tmp_path)

    # Should not raise
    ingester.delete_repo("nonexistent")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/repo/test_ingester.py -v -k "delete_repo"`
Expected: FAIL with "AttributeError: 'RepoIngester' object has no attribute 'delete_repo'"

**Step 3: Write minimal implementation**

```python
def delete_repo(self, project_id: str) -> None:
    """Delete the cloned repository directory for a project."""
    repo_path = self.repos_dir / project_id
    if repo_path.exists():
        shutil.rmtree(repo_path)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/repo/test_ingester.py -v -k "delete_repo"`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/repo/ingester.py tests/unit/repo/test_ingester.py
git commit -m "feat(repo): add delete_repo method"
```

---

### Task 3: Save source URL when ingesting repos

**Files:**
- Modify: `src/shesha/shesha.py:317-319`
- Test: `tests/unit/test_shesha.py`

**Step 1: Write the failing test**

```python
# Add to TestCreateProjectFromRepo class:

def test_saves_source_url_for_local_repo(self, tmp_path: Path):
    """create_project_from_repo saves source URL for local repos."""
    with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
        with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
            mock_ingester = MagicMock()
            mock_ingester_cls.return_value = mock_ingester

            mock_ingester.is_local_path.return_value = True
            mock_ingester.get_saved_sha.return_value = None
            mock_ingester.get_sha_from_path.return_value = "abc123"
            mock_ingester.list_files_from_path.return_value = []
            mock_ingester.repos_dir = tmp_path / "repos"

            shesha = Shesha(model="test-model", storage_path=tmp_path)
            shesha.create_project_from_repo(
                url="/path/to/local/repo",
                name="my-project",
            )

            mock_ingester.save_source_url.assert_called_once_with(
                "my-project", "/path/to/local/repo"
            )
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_shesha.py::TestCreateProjectFromRepo::test_saves_source_url_for_local_repo -v`
Expected: FAIL with "Expected call: save_source_url('my-project', '/path/to/local/repo')"

**Step 3: Write minimal implementation**

In `src/shesha/shesha.py`, in the `_ingest_repo` method after `self._repo_ingester.save_sha(name, sha)` (around line 319), add:

```python
        # Save source URL for later retrieval
        self._repo_ingester.save_source_url(name, url)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_shesha.py::TestCreateProjectFromRepo::test_saves_source_url_for_local_repo -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/shesha.py tests/unit/test_shesha.py
git commit -m "feat: save source URL when ingesting repos"
```

---

### Task 4: Add ProjectInfo dataclass

**Files:**
- Modify: `src/shesha/models.py`
- Test: `tests/unit/test_models.py`

**Step 1: Write the failing test**

```python
# Add to tests/unit/test_models.py:

from shesha.models import ProjectInfo


def test_project_info_dataclass():
    """ProjectInfo stores project metadata correctly."""
    info = ProjectInfo(
        project_id="my-project",
        source_url="https://github.com/org/repo",
        is_local=False,
        source_exists=True,
    )

    assert info.project_id == "my-project"
    assert info.source_url == "https://github.com/org/repo"
    assert info.is_local is False
    assert info.source_exists is True


def test_project_info_with_none_source():
    """ProjectInfo handles None source_url for non-repo projects."""
    info = ProjectInfo(
        project_id="manual-project",
        source_url=None,
        is_local=False,
        source_exists=True,
    )

    assert info.source_url is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_models.py -v -k "project_info"`
Expected: FAIL with "ImportError: cannot import name 'ProjectInfo'"

**Step 3: Write minimal implementation**

In `src/shesha/models.py`, add after the imports:

```python
@dataclass
class ProjectInfo:
    """Metadata about a project's source."""

    project_id: str
    source_url: str | None
    is_local: bool
    source_exists: bool
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_models.py -v -k "project_info"`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/models.py tests/unit/test_models.py
git commit -m "feat: add ProjectInfo dataclass"
```

---

### Task 5: Export ProjectInfo in public API

**Files:**
- Modify: `src/shesha/__init__.py`
- Test: `tests/unit/test_public_api.py`

**Step 1: Write the failing test**

```python
# Add to tests/unit/test_public_api.py:

def test_project_info_exported():
    """ProjectInfo is exported from the public API."""
    from shesha import ProjectInfo

    assert ProjectInfo is not None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_public_api.py -v -k "project_info"`
Expected: FAIL with "ImportError: cannot import name 'ProjectInfo'"

**Step 3: Write minimal implementation**

In `src/shesha/__init__.py`:

1. Add to the imports: `from shesha.models import ParsedDocument, ProjectInfo, QueryContext, RepoProjectResult`
2. Add `"ProjectInfo",` to the `__all__` list (after `"ParsedDocument",`)

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_public_api.py -v -k "project_info"`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/__init__.py tests/unit/test_public_api.py
git commit -m "feat: export ProjectInfo in public API"
```

---

### Task 6: Add get_project_info method to Shesha

**Files:**
- Modify: `src/shesha/shesha.py`
- Test: `tests/unit/test_shesha.py`

**Step 1: Write the failing test**

```python
# Add new test class to tests/unit/test_shesha.py:

class TestGetProjectInfo:
    """Tests for get_project_info method."""

    def test_returns_info_for_remote_repo(self, tmp_path: Path):
        """get_project_info returns correct info for remote repo project."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
                mock_ingester.is_local_path.return_value = False

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha._storage.create_project("my-project")

                info = shesha.get_project_info("my-project")

                assert info.project_id == "my-project"
                assert info.source_url == "https://github.com/org/repo"
                assert info.is_local is False
                assert info.source_exists is True

    def test_returns_info_for_existing_local_repo(self, tmp_path: Path):
        """get_project_info returns source_exists=True when local path exists."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                local_path = tmp_path / "local_repo"
                local_path.mkdir()

                mock_ingester.get_source_url.return_value = str(local_path)
                mock_ingester.is_local_path.return_value = True

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha._storage.create_project("local-project")

                info = shesha.get_project_info("local-project")

                assert info.is_local is True
                assert info.source_exists is True

    def test_returns_info_for_missing_local_repo(self, tmp_path: Path):
        """get_project_info returns source_exists=False when local path missing."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.get_source_url.return_value = "/nonexistent/path"
                mock_ingester.is_local_path.return_value = True

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha._storage.create_project("missing-project")

                info = shesha.get_project_info("missing-project")

                assert info.is_local is True
                assert info.source_exists is False

    def test_raises_for_nonexistent_project(self, tmp_path: Path):
        """get_project_info raises ValueError for non-existent project."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            shesha = Shesha(model="test-model", storage_path=tmp_path)

            with pytest.raises(ValueError) as exc_info:
                shesha.get_project_info("nonexistent")

            assert "does not exist" in str(exc_info.value)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_shesha.py::TestGetProjectInfo -v`
Expected: FAIL with "AttributeError: 'Shesha' object has no attribute 'get_project_info'"

**Step 3: Write minimal implementation**

In `src/shesha/shesha.py`:

1. Add to imports: `from shesha.models import ParsedDocument, ProjectInfo, RepoProjectResult`
2. Add method after `delete_project`:

```python
def get_project_info(self, project_id: str) -> ProjectInfo:
    """Get metadata about a project.

    Args:
        project_id: ID of the project.

    Returns:
        ProjectInfo with source URL, whether it's local, and source existence.

    Raises:
        ValueError: If project doesn't exist.
    """
    if not self._storage.project_exists(project_id):
        raise ValueError(f"Project '{project_id}' does not exist")

    source_url = self._repo_ingester.get_source_url(project_id)

    if source_url is None:
        return ProjectInfo(
            project_id=project_id,
            source_url=None,
            is_local=False,
            source_exists=True,
        )

    is_local = self._repo_ingester.is_local_path(source_url)

    if is_local:
        source_exists = Path(source_url).expanduser().exists()
    else:
        source_exists = True  # Remote repos always "exist"

    return ProjectInfo(
        project_id=project_id,
        source_url=source_url,
        is_local=is_local,
        source_exists=source_exists,
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_shesha.py::TestGetProjectInfo -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/shesha.py tests/unit/test_shesha.py
git commit -m "feat: add get_project_info method to Shesha"
```

---

### Task 7: Enhance delete_project with cleanup_repo parameter

**Files:**
- Modify: `src/shesha/shesha.py:129-131`
- Test: `tests/unit/test_shesha.py`

**Step 1: Write the failing test**

```python
# Add to TestShesha class:

def test_delete_project_cleans_up_remote_repo(self, tmp_path: Path):
    """delete_project removes cloned repo for remote projects by default."""
    with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
        with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
            mock_ingester = MagicMock()
            mock_ingester_cls.return_value = mock_ingester

            mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
            mock_ingester.is_local_path.return_value = False

            shesha = Shesha(model="test-model", storage_path=tmp_path)
            shesha._storage.create_project("to-delete")

            shesha.delete_project("to-delete")

            mock_ingester.delete_repo.assert_called_once_with("to-delete")


def test_delete_project_skips_cleanup_for_local_repo(self, tmp_path: Path):
    """delete_project does not call delete_repo for local repos."""
    with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
        with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
            mock_ingester = MagicMock()
            mock_ingester_cls.return_value = mock_ingester

            mock_ingester.get_source_url.return_value = "/path/to/local/repo"
            mock_ingester.is_local_path.return_value = True

            shesha = Shesha(model="test-model", storage_path=tmp_path)
            shesha._storage.create_project("local-project")

            shesha.delete_project("local-project")

            mock_ingester.delete_repo.assert_not_called()


def test_delete_project_respects_cleanup_repo_false(self, tmp_path: Path):
    """delete_project skips repo cleanup when cleanup_repo=False."""
    with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
        with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
            mock_ingester = MagicMock()
            mock_ingester_cls.return_value = mock_ingester

            mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
            mock_ingester.is_local_path.return_value = False

            shesha = Shesha(model="test-model", storage_path=tmp_path)
            shesha._storage.create_project("to-delete")

            shesha.delete_project("to-delete", cleanup_repo=False)

            mock_ingester.delete_repo.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_shesha.py::TestShesha::test_delete_project_cleans_up_remote_repo -v`
Expected: FAIL with "AssertionError: Expected call: delete_repo('to-delete')"

**Step 3: Write minimal implementation**

Replace the existing `delete_project` method in `src/shesha/shesha.py`:

```python
def delete_project(self, project_id: str, *, cleanup_repo: bool = True) -> None:
    """Delete a project and optionally its cloned repository.

    Args:
        project_id: Project to delete.
        cleanup_repo: If True (default), also removes cloned repo data
            for remote repositories. Has no effect for projects
            created from local paths.
    """
    if cleanup_repo:
        source_url = self._repo_ingester.get_source_url(project_id)
        if source_url and not self._repo_ingester.is_local_path(source_url):
            self._repo_ingester.delete_repo(project_id)

    self._storage.delete_project(project_id)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_shesha.py::TestShesha -v -k "delete_project"`
Expected: PASS (all delete_project tests)

**Step 5: Commit**

```bash
git add src/shesha/shesha.py tests/unit/test_shesha.py
git commit -m "feat: enhance delete_project with cleanup_repo parameter"
```

---

### Task 8: Update repo.py picker to show missing status

**Files:**
- Modify: `examples/repo.py:119-164`
- Test: `tests/unit/test_repo_script.py`

**Step 1: Write the failing test**

```python
# Add to tests/unit/test_repo_script.py:

def test_show_picker_shows_missing_marker(capsys, monkeypatch):
    """show_picker marks projects with missing local repos."""
    from examples.repo import show_picker
    from shesha import ProjectInfo

    mock_shesha = MagicMock()
    mock_shesha.list_projects.return_value = ["remote-repo", "missing-local"]
    mock_shesha.get_project_info.side_effect = [
        ProjectInfo("remote-repo", "https://github.com/org/repo", False, True),
        ProjectInfo("missing-local", "/old/path", True, False),
    ]

    monkeypatch.setattr("builtins.input", lambda _: "1")

    show_picker(mock_shesha)

    captured = capsys.readouterr()
    assert "missing-local (missing - /old/path)" in captured.out
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_repo_script.py -v -k "missing_marker"`
Expected: FAIL (either import error or assertion failure)

**Step 3: Write minimal implementation**

In `examples/repo.py`, modify `show_picker` function:

```python
def show_picker(shesha: Shesha) -> tuple[str, bool] | None:
    """Show interactive repository picker for previously indexed repos.

    Displays a numbered list of previously indexed repositories and prompts
    the user to either select one by number, delete one with 'd<N>', or
    enter a new URL/path.

    Args:
        shesha: Initialized Shesha instance to query for existing projects.

    Returns:
        None: If no projects exist in storage.
        tuple[str, True]: If user selected an existing project (project name).
        tuple[str, False]: If user entered a new URL/path to index.
    """
    projects = shesha.list_projects()
    if not projects:
        return None

    print("Available repositories:")
    for i, name in enumerate(projects, 1):
        info = shesha.get_project_info(name)
        if info.is_local and not info.source_exists:
            print(f"  {i}. {name} (missing - {info.source_url})")
        else:
            print(f"  {i}. {name}")
    print()

    user_input = input("Enter number, 'd<N>' to delete, or new URL: ").strip()

    # Check if it's a number selecting an existing project
    try:
        num = int(user_input)
        if 1 <= num <= len(projects):
            return (projects[num - 1], True)
    except ValueError:
        pass

    # Otherwise treat as new URL/path
    return (user_input, False)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_repo_script.py -v -k "missing_marker"`
Expected: PASS

**Step 5: Commit**

```bash
git add examples/repo.py tests/unit/test_repo_script.py
git commit -m "feat(repo.py): show missing marker for local repos that no longer exist"
```

---

### Task 9: Add deletion flow to repo.py picker

**Files:**
- Modify: `examples/repo.py:119-164`
- Test: `tests/unit/test_repo_script.py`

**Step 1: Write the failing test**

```python
def test_show_picker_handles_delete_command(capsys, monkeypatch):
    """show_picker handles 'd<N>' delete commands."""
    from examples.repo import show_picker
    from shesha import ProjectInfo

    mock_shesha = MagicMock()
    # First call: show list with 2 items, user enters 'd1'
    # Second call: show list with 1 item, user enters '1'
    mock_shesha.list_projects.side_effect = [
        ["project-a", "project-b"],
        ["project-b"],
    ]
    mock_shesha.get_project_info.side_effect = [
        ProjectInfo("project-a", "https://github.com/org/a", False, True),
        ProjectInfo("project-b", "https://github.com/org/b", False, True),
        # After deletion:
        ProjectInfo("project-b", "https://github.com/org/b", False, True),
    ]

    inputs = iter(["d1", "y", "1"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    result = show_picker(mock_shesha)

    mock_shesha.delete_project.assert_called_once_with("project-a")
    assert result == ("project-b", True)
    captured = capsys.readouterr()
    assert "Deleted 'project-a'" in captured.out


def test_show_picker_delete_with_confirmation_no(capsys, monkeypatch):
    """show_picker cancels delete when user says no."""
    from examples.repo import show_picker
    from shesha import ProjectInfo

    mock_shesha = MagicMock()
    mock_shesha.list_projects.side_effect = [
        ["project-a"],
        ["project-a"],
    ]
    mock_shesha.get_project_info.return_value = ProjectInfo(
        "project-a", "https://github.com/org/a", False, True
    )

    inputs = iter(["d1", "n", "1"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    result = show_picker(mock_shesha)

    mock_shesha.delete_project.assert_not_called()
    assert result == ("project-a", True)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_repo_script.py -v -k "delete_command"`
Expected: FAIL (delete command not recognized)

**Step 3: Write minimal implementation**

Replace `show_picker` in `examples/repo.py`:

```python
def show_picker(shesha: Shesha) -> tuple[str, bool] | None:
    """Show interactive repository picker for previously indexed repos.

    Displays a numbered list of previously indexed repositories and prompts
    the user to either select one by number, delete one with 'd<N>', or
    enter a new URL/path.

    Args:
        shesha: Initialized Shesha instance to query for existing projects.

    Returns:
        None: If no projects exist in storage.
        tuple[str, True]: If user selected an existing project (project name).
        tuple[str, False]: If user entered a new URL/path to index.
    """
    while True:
        projects = shesha.list_projects()
        if not projects:
            return None

        print("Available repositories:")
        project_infos = []
        for i, name in enumerate(projects, 1):
            info = shesha.get_project_info(name)
            project_infos.append(info)
            if info.is_local and not info.source_exists:
                print(f"  {i}. {name} (missing - {info.source_url})")
            else:
                print(f"  {i}. {name}")
        print()

        user_input = input("Enter number, 'd<N>' to delete, or new URL: ").strip()

        # Check for delete command
        if user_input.lower().startswith("d"):
            try:
                num = int(user_input[1:])
                if 1 <= num <= len(projects):
                    project_name = projects[num - 1]
                    info = project_infos[num - 1]

                    # Determine confirmation message
                    if info.is_local or info.source_url is None:
                        msg = f"Delete '{project_name}'? This will remove all indexed data. (y/n): "
                    else:
                        msg = f"Delete '{project_name}'? This will remove indexed data and cloned repository. (y/n): "

                    confirm = input(msg).strip().lower()
                    if confirm == "y":
                        shesha.delete_project(project_name)
                        print(f"Deleted '{project_name}'.")
                    print()
                    continue  # Re-show picker
            except ValueError:
                pass

        # Check if it's a number selecting an existing project
        try:
            num = int(user_input)
            if 1 <= num <= len(projects):
                return (projects[num - 1], True)
        except ValueError:
            pass

        # Otherwise treat as new URL/path
        return (user_input, False)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_repo_script.py -v -k "delete"`
Expected: PASS

**Step 5: Commit**

```bash
git add examples/repo.py tests/unit/test_repo_script.py
git commit -m "feat(repo.py): add deletion flow with confirmation to picker"
```

---

### Task 10: Run full test suite and verify

**Files:**
- None (verification only)

**Step 1: Run full test suite**

Run: `make all`
Expected: All tests pass, no lint errors, no type errors

**Step 2: Manual verification**

Test the feature manually:
```bash
# Create a test project from a local repo
python examples/repo.py /path/to/some/repo

# Exit and re-run to see picker
python examples/repo.py

# Try deleting with 'd1'
# Verify confirmation prompt appears
# Verify deletion works
```

**Step 3: Commit any fixes if needed**

If any issues found, fix and commit.

---

### Task 11: Update CHANGELOG

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add changelog entry**

Add under `[Unreleased]`:

```markdown
### Added
- `ProjectInfo` dataclass for project metadata
- `Shesha.get_project_info()` method to retrieve project source information
- Repo picker now shows "(missing - /path)" for local repos that no longer exist
- Repo picker supports `d<N>` command to delete projects with confirmation

### Changed
- `Shesha.delete_project()` now accepts `cleanup_repo` parameter (default `True`) to also remove cloned repository data for remote repos
```

**Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for repo removal feature"
```
