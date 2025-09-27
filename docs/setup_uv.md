## Migrating from Poetry to uv for Dependency Management

Follow these steps to switch your Python project from Poetry to uv, using pyenv and VS Code:

### 1. Install uv

```sh
brew install uv
# or
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Deactivate and Remove the Old Poetry Environment

If you have an active Poetry environment, deactivate it:

```sh
deactivate
```

List Poetry environments and remove the old one:

```sh
poetry env list
poetry env remove <env-name-from-list>
# Example:
# poetry env remove progress-NPFUFRU0-py3.12
```

### 3. Ensure pyenv is Set (if using pyenv)

Check your Python version:

```sh
pyenv local
python -V
```
Make sure it matches your project’s required version.

### 4. Create a New uv Virtual Environment

If using pyenv:

```sh
uv venv --python $(pyenv which python) .venv
```
If not using pyenv:

```sh
uv venv .venv
```

### 5. Activate the New Environment

```sh
source .venv/bin/activate
```
You should see `(.venv)` in your shell prompt.

### 6. Set VS Code to Use the New Interpreter

In VS Code, open the Command Palette and select:
> Python: Select Interpreter
Choose `.venv/bin/python` from the list.

### 7. Install All Dependencies

```sh
uv sync --all-extras
```

### 8. Test Your Setup

Run the following commands to verify everything works:

```sh
uv run pytest
uv run ruff
```

### 9. Update VS Code Workspace Settings

1. Remove the Poetry path from `.vscode/settings.json`:
	```jsonc
	// Remove this line if present:
	"python.poetryPath": "poetry",
	```
2. Restart VS Code to ensure it picks up the new environment.
3. Confirm the interpreter in the lower right is set to `.venv` and that new terminals use the correct environment.

### 10. Debugging

Test debugging in VS Code to ensure it uses the `.venv` environment.

---


