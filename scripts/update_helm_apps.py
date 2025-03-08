#!/usr/bin/env -S uv run --quiet --locked --script --no-cache
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "requests",
#     "typer",
#     "rich",
#     "ruamel.yaml",
# ]
# ///

from pathlib import Path
import subprocess
from typing import Any, Optional
from ruamel.yaml import YAML
from rich import print as rprint
from rich.table import Table
from rich.console import Console
from rich.syntax import Syntax
import json
from io import StringIO
import difflib
import typer

app = typer.Typer()
console = Console()

# Use ruamel.yaml for safer YAML parsing and round-trip
yaml = YAML(typ='rt')
yaml.default_flow_style = False
yaml.preserve_quotes = True
yaml.width = 4096  # Prevent line wrapping

APPS_DIRS = [
    "argo-apps/core-apps",
    "argo-apps/apps",
    "argo-apps/fokais",
]


class ArgoApp:
    """Simple class to hold Argo CD application info"""
    def __init__(self, file: Path, data: dict):
        self.file = file
        self.data = data
        spec = data.get('spec', {})
        
        # Basic app info
        self.name = spec.get('name', file.stem)
        destination = spec.get('destination', {})
        self.namespace = destination.get('namespace', 'default')
        self.project = spec.get('project', 'default')
        
        # Source info
        source = spec.get('source', {})
        self.chart = source.get('chart')
        self.repo_url = source.get('repoURL')
        self.target_revision = source.get('targetRevision')
        self.path = source.get('path')
        
        # Latest version info
        self._latest_version = None

    @property
    def is_helm(self) -> bool:
        """Check if this is a helm chart source"""
        return bool(self.chart and self.repo_url and self.target_revision)
    
    @property
    def latest_version(self) -> Optional[str]:
        """Get latest version, fetching it if not already cached"""
        if self._latest_version is None and self.is_helm:
            self._latest_version = get_latest_chart_version(self.repo_url, self.chart)
        return self._latest_version
    
    @property
    def needs_update(self) -> bool:
        """Check if app needs updating"""
        return bool(
            self.is_helm 
            and self.latest_version 
            and self.latest_version != self.target_revision
        )
    
    def update_version(self, new_version: str) -> None:
        """Update the version in the data"""
        if 'spec' not in self.data:
            self.data['spec'] = {}
        if 'source' not in self.data['spec']:
            self.data['spec']['source'] = {}
        self.data['spec']['source']['targetRevision'] = new_version
        self.target_revision = new_version


def show_yaml_diff(old_yaml: str, new_yaml: str, title: str) -> None:
    """Show a diff between two YAML strings"""
    console.print(f"\n[bold]{title}[/bold]")
    
    diff = difflib.unified_diff(
        old_yaml.splitlines(keepends=True),
        new_yaml.splitlines(keepends=True),
        fromfile='current',
        tofile='updated',
    )
    
    for line in diff:
        if line.startswith('+'):
            rprint(f"[green]{line}[/green]", end='')
        elif line.startswith('-'):
            rprint(f"[red]{line}[/red]", end='')
        else:
            rprint(line, end='')


def update_app_version(app: ArgoApp, dry_run: bool = True) -> bool:
    """Update an app's version, showing diff in dry run mode"""
    if not app.needs_update:
        return False
    
    # Get the current YAML content
    with open(app.file) as f:
        current_content = f.read()
    
    # Create updated YAML
    app.update_version(app.latest_version)
    
    # Convert to string while preserving formatting
    stream = StringIO()
    yaml.dump(app.data, stream)
    new_content = stream.getvalue()
    
    # Show diff
    show_yaml_diff(
        current_content,
        new_content,
        f"Update {app.name} from {app.target_revision} to {app.latest_version}"
    )
    
    if not dry_run:
        # Write the changes
        with open(app.file, 'w') as f:
            f.write(new_content)
        return True
    
    return False


def run_helm_command(cmd: list[str]) -> tuple[int, str]:
    """Run a helm command and return output"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        return 0, result.stdout
    except subprocess.CalledProcessError as e:
        return e.returncode, e.stderr
    except Exception as e:
        return 1, str(e)


def add_helm_repo(repo_url: str, repo_name: str) -> bool:
    """Add a helm repo if not already added"""
    # Check if repo exists
    code, output = run_helm_command(['helm', 'repo', 'list', '-o', 'json'])
    if code == 0:
        try:
            repos = json.loads(output)
            for repo in repos:
                if repo.get('url') == repo_url:
                    return True
        except Exception:
            pass
        
    # Add repo
    code, err = run_helm_command(['helm', 'repo', 'add', repo_name, repo_url])
    if code != 0:
        rprint(f"[yellow]Warning: Failed to add repo {repo_url}: {err}[/yellow]")
        return False
    
    return True


def get_latest_chart_version(repo_url: str, chart_name: str) -> Optional[str]:
    """Get the latest version for a chart"""
    # Extract repo name from URL - handle common formats
    repo_name = repo_url.rstrip('/').split('/')[-1]
    if '.' in repo_name:
        repo_name = repo_name.split('.')[0]
    if repo_name == 'helm':  # Special case for URLs ending in /helm
        repo_name = repo_url.rstrip('/').split('/')[-2]
    
    # Special cases for known repos
    if repo_url == 'https://argoproj.github.io/argo-helm':
        repo_name = 'argo'
    
    # Debug output
    rprint(f"[dim]Looking up {chart_name} in {repo_name} ({repo_url})[/dim]")
    
    # Add repo if needed
    if not add_helm_repo(repo_url, repo_name):
        return None
    
    # Update repo
    code, err = run_helm_command(['helm', 'repo', 'update'])
    if code != 0:
        rprint(f"[yellow]Warning: Failed to update repos: {err}[/yellow]")
        return None
    
    # Search for chart
    search_name = f"{repo_name}/{chart_name}"
    rprint(f"[dim]Searching for {search_name}[/dim]")
    
    code, output = run_helm_command([
        'helm', 'search', 'repo',
        search_name,
        '--output', 'json',
        '--version', '*',  # Show all versions
    ])
    
    if code != 0:
        rprint(f"[yellow]Warning: Failed to search for {search_name}: {output}[/yellow]")
        return None
    
    try:
        results = json.loads(output)
        if results:
            # Sort versions and get the latest
            versions = sorted(
                results,
                key=lambda x: x['version'].lstrip('v'),
                reverse=True
            )
            return versions[0]['version']
        else:
            rprint(f"[yellow]Warning: No versions found for {search_name}[/yellow]")
    except Exception as e:
        rprint(f"[yellow]Warning: Failed to parse helm search output: {e}[/yellow]")
    
    return None


def load_yaml_file(file_path: Path) -> list[dict]:
    """Load a YAML file safely"""
    try:
        with open(file_path) as f:
            content = f.read()
            
        # Split documents and parse each one
        docs = []
        for doc in content.split('---'):
            if not doc.strip():
                continue
            try:
                data = yaml.load(doc)
                if isinstance(data, dict):
                    docs.append(data)
            except Exception:
                continue
        return docs
    except Exception as e:
        rprint(f"[yellow]Warning: Error reading {file_path}: {e}[/yellow]")
        return []


def list_all_apps() -> list[ArgoApp]:
    """List all ArgoApps from the APPS_DIRS"""
    apps = []
    for apps_dir in APPS_DIRS:
        app_dir = Path(apps_dir)
        if not app_dir.exists():
            continue
        
        for yaml_file in app_dir.glob("*.yaml"):
            for doc in load_yaml_file(yaml_file):
                if not isinstance(doc, dict):
                    continue
                try:
                    app = ArgoApp(yaml_file, doc)
                    apps.append(app)
                except Exception as e:
                    rprint(f"[yellow]Warning: Failed to parse {yaml_file}: {e}[/yellow]")
    
    return apps


def list_all_helm_apps() -> list[ArgoApp]:
    """Filter all ArgoApps to only those that use helm"""
    apps = list_all_apps()
    return [app for app in apps if app.is_helm]


def run_git_command(cmd: list[str]) -> tuple[int, str]:
    """Run a git command and return exit code and output"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode, result.stdout or result.stderr
    except Exception as e:
        return 1, str(e)


def check_git_status(files: list[Path]) -> tuple[bool, list[Path]]:
    """Check if any files have uncommitted changes
    
    Returns:
        tuple: (clean, modified_files)
    """
    # Get status of specific files
    code, output = run_git_command(['git', 'status', '--porcelain'] + [str(f) for f in files])
    if code != 0:
        rprint(f"[red]Error checking git status: {output}[/red]")
        return False, []
    
    # Parse status output
    modified = []
    for line in output.splitlines():
        if not line.strip():
            continue
        status = line[:2]
        file_path = line[3:].strip()
        if status != '  ':  # Any status other than unmodified
            modified.append(Path(file_path))
    
    return len(modified) == 0, modified


def stage_files(files: list[Path]) -> bool:
    """Stage files for commit"""
    code, output = run_git_command(['git', 'add'] + [str(f) for f in files])
    if code != 0:
        rprint(f"[red]Error staging files: {output}[/red]")
        return False
    return True


@app.command()
def list(helm: bool = False):
    """List all Argo CD applications"""
    if helm:
        apps = list_all_helm_apps()
        title = "Helm-based Argo CD Applications"
    else:
        apps = list_all_apps()
        title = "All Argo CD Applications"

    table = Table(title=title)
    table.add_column("Name")
    table.add_column("Namespace")
    table.add_column("Type")
    table.add_column("Chart")
    table.add_column("Current")
    table.add_column("Latest")
    table.add_column("Status")

    for app in apps:
        if app.is_helm:
            type_ = "Helm"
            chart = app.chart
            current = app.target_revision
            latest = app.latest_version or "Unknown"
            status = "[yellow]⟳[/yellow]" if app.needs_update else "[green]✓[/green]"
        else:
            type_ = "Path"
            chart = app.path or "N/A"
            current = "N/A"
            latest = "N/A"
            status = ""

        table.add_row(
            app.name,
            app.namespace,
            type_,
            chart,
            current,
            latest,
            status,
        )

    console.print(table)


@app.command()
def update(
    dry_run: bool = True,
    helm: bool = True,
    all: bool = False,
    app_name: str = None,
):
    """Update helm chart versions
    
    Args:
        dry_run: Show what would change without making changes
        helm: Only update helm charts
        all: Update all apps that need updates
        app_name: Update a specific app by name
    """
    apps = list_all_helm_apps() if helm else list_all_apps()
    
    # Filter to specific app if requested
    if app_name:
        apps = [app for app in apps if app.name == app_name]
        if not apps:
            rprint(f"[red]Error: No app found with name {app_name}[/red]")
            return
    
    # Find apps that need updates
    updates_needed = [app for app in apps if app.needs_update]
    if not updates_needed:
        rprint("[green]All apps are up to date![/green]")
        return
    
    # Check git status first
    files_to_update = [app.file for app in updates_needed]
    is_clean, modified = check_git_status(files_to_update)
    if not is_clean:
        rprint("[red]Error: The following files have uncommitted changes:[/red]")
        for f in modified:
            rprint(f"  - {f}")
        rprint("\nPlease commit or stash changes before updating.")
        return
    
    # Show summary of updates
    table = Table(title="Updates Available")
    table.add_column("Name")
    table.add_column("Current")
    table.add_column("Latest")
    
    for app in updates_needed:
        table.add_row(
            app.name,
            app.target_revision,
            app.latest_version,
        )
    
    console.print(table)
    console.print()
    
    # Confirm and update
    if not all and not app_name:
        rprint("[yellow]Use --all to update all apps or specify an app with --app-name[/yellow]")
        return
    
    # Show diffs and update
    updated = []
    for app in updates_needed:
        if update_app_version(app, dry_run=dry_run):
            updated.append(app)
    
    # Stage files if we made changes
    if not dry_run and updated:
        files_updated = [app.file for app in updated]
        if stage_files(files_updated):
            rprint("\n[green]Files staged for commit:[/green]")
            for f in files_updated:
                rprint(f"  - {f}")
        else:
            rprint("\n[yellow]Warning: Failed to stage files[/yellow]")
    
    # Show summary
    if dry_run:
        rprint("\n[yellow]Dry run - no changes made[/yellow]")
    else:
        rprint(f"\n[green]Updated {len(updated)} apps[/green]")


if __name__ == "__main__":
    app()
