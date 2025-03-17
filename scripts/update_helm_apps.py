#!/usr/bin/env -S uv run --quiet --locked --script --no-cache
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "requests",
#     "typer",
#     "rich",
#     "pyyaml",
#     "packaging",
# ]
# ///

from pathlib import Path
import subprocess
from typing import Any, Optional
from io import StringIO
import yaml
from rich import print as rprint
from rich.table import Table
from rich.console import Console
from rich.syntax import Syntax
from rich.live import Live
from rich.spinner import Spinner
from rich.panel import Panel
from rich.align import Align
import json
import difflib
import typer
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import partial
import threading
from contextlib import nullcontext
import re
import requests
from packaging import version
from urllib.parse import urlparse

app = typer.Typer()
console = Console()

APPS_DIRS = [
    "argo-apps/core-apps",
    "argo-apps/apps",
    "argo-apps/fokais",
]


class ArgoApp:
    """Simple class to hold Argo CD application info"""
    def __init__(self, file: Path, data: dict, verbose: bool = False):
        self.file = file
        self.data = data
        self.verbose = verbose
        spec = data.get('spec', {})
        
        # Basic app info
        self.name = data.get('metadata', {}).get('name', file.stem)
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
            self._latest_version = get_latest_chart_version(
                self.repo_url,
                self.chart,
                verbose=self.verbose
            )
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


def parse_version(ver: str) -> version.Version:
    """Parse a version string into a Version object for comparison"""
    # Remove 'v' prefix if present
    ver = ver.lstrip('v')
    try:
        return version.parse(ver)
    except version.InvalidVersion:
        # If parsing fails, return a very old version
        return version.parse('0.0.0')


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
    lines = []
    
    # Dump main application
    lines.append('---\n')
    main_yaml = yaml.safe_dump(app.data, default_flow_style=False, sort_keys=False)
    lines.append(main_yaml)
    
    # Dump additional resources if present
    if '__additional_resources' in app.data:
        additional = app.data.pop('__additional_resources')  # Remove from main doc
        for doc in additional:
            lines.append('---\n')
            lines.append(doc)  # Use original document text
            
    new_content = ''.join(lines)
    
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


def run_helm_command(cmd: list[str], verbose: bool = False) -> tuple[int, str]:
    """Run a helm command and return exit code and output"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if verbose and result.stdout:
            rprint(result.stdout.strip())
        return result.returncode, result.stdout or result.stderr
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


def get_repo_name_from_url(repo_url: str) -> str:
    """Generate a consistent, unique repo name from a URL"""
    # Normalize the URL
    url = repo_url.rstrip('/').lower()
    
    # Parse URL into components
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split('/') if p]
    
    if 'github.io' in parsed.netloc:
        # For GitHub Pages URLs (e.g. https://org.github.io/repo)
        # Use the org name as it's typically more stable and unique
        org = parsed.netloc.split('.')[0]
        return org
    elif len(path_parts) >= 2 and any(domain in parsed.netloc for domain in ['github.com', 'gitlab.com', 'bitbucket.org']):
        # For direct repo URLs (e.g. https://github.com/org/repo)
        # Use the org name as it's typically more stable and unique
        return path_parts[0]
    elif 'raw.githubusercontent.com' in parsed.netloc:
        # For raw GitHub URLs (e.g. https://raw.githubusercontent.com/org/repo/...)
        # Use the org name
        return path_parts[0]
    else:
        # For other URLs, use the hostname without common prefixes/suffixes
        name = parsed.netloc.split('.')[0]
        if name in ['www', 'charts']:
            name = parsed.netloc.split('.')[1]
        return name


def get_index_url(repo_url: str) -> str:
    """Get the URL for the index.yaml file"""
    # Normalize the URL
    url = repo_url.rstrip('/')
    
    # Special case for raw GitHub URLs
    if 'raw.githubusercontent.com' in url:
        # Convert /master/charts to /refs/heads/master/charts
        if '/master/charts' in url:
            url = url.replace('/master/charts', '/refs/heads/master/charts')
        # Add index.yaml if not present
        if not url.endswith('index.yaml'):
            url = f"{url}/index.yaml"
    else:
        # For normal Helm repos, just append index.yaml
        url = f"{url}/index.yaml"
    
    return url


def get_latest_chart_version(repo_url: str, chart_name: str, verbose: bool = False) -> Optional[str]:
    """Get the latest version for a chart"""
    # Generate repo name from URL
    repo_name = get_repo_name_from_url(repo_url)
    
    # Clean up the name to be valid and simple
    repo_name = re.sub(r'[^a-zA-Z0-9-]', '-', repo_name).lower()
    repo_name = re.sub(r'-+', '-', repo_name)  # Replace multiple hyphens with single
    repo_name = repo_name.strip('-')  # Remove leading/trailing hyphens
    
    if verbose:
        rprint(f"Looking up {chart_name} in {repo_name} ({repo_url})")
    
    # For GitHub release-based charts, try to get the index file directly
    if any(url in repo_url for url in ['github.io', 'clustersecret.com']) or 'raw.githubusercontent.com' in repo_url:
        try:
            # Get the index file
            index_url = get_index_url(repo_url)
            response = requests.get(index_url)
            if response.status_code == 200:
                index = yaml.safe_load(response.text)
                if chart_name in index.get('entries', {}):
                    versions = sorted(
                        [entry['version'] for entry in index['entries'][chart_name]],
                        key=lambda x: parse_version(x),
                        reverse=True
                    )
                    if versions:
                        return versions[0]
        except Exception as e:
            if verbose:
                rprint(f"[yellow]Warning: Failed to fetch index directly: {e}[/yellow]")
    
    # Add repo if needed (fallback to standard helm commands)
    if not add_helm_repo(repo_url, repo_name):
        return None
    
    # Update repo
    code, err = run_helm_command(['helm', 'repo', 'update'])
    if code != 0:
        rprint(f"[yellow]Warning: Failed to update repos: {err}[/yellow]")
        return None
    
    # Search for chart
    search_name = f"{repo_name}/{chart_name}"
    if verbose:
        rprint(f"Searching for {search_name}")
    
    code, output = run_helm_command([
        'helm', 'search', 'repo',
        search_name,
        '--output', 'json',
        '--version', '*',  # Show all versions
    ])
    
    if code != 0:
        if verbose:
            rprint(f"[yellow]Warning: Failed to search for {search_name}: {output}[/yellow]")
        return None
    
    try:
        results = json.loads(output)
        if results:
            # Sort versions and get the latest
            versions = sorted(
                results,
                key=lambda x: parse_version(x['version']),
                reverse=True
            )
            return versions[0]['version']
        else:
            if verbose:
                rprint(f"[yellow]Warning: No versions found for {search_name}[/yellow]")
    except Exception as e:
        if verbose:
            rprint(f"[yellow]Warning: Failed to parse helm search output: {e}[/yellow]")
    
    return None


def load_yaml_file(file_path: Path) -> dict:
    """Load a YAML file safely"""
    try:
        with open(file_path) as f:
            content = f.read()
            
        # Split into documents while preserving empty lines and indentation
        docs = []
        current_doc = []
        
        for line in content.splitlines(True):  # Keep line endings
            if line.rstrip() == '---':
                if current_doc:
                    docs.append(''.join(current_doc))
                current_doc = []
            else:
                current_doc.append(line)
                
        if current_doc:
            docs.append(''.join(current_doc))
            
        if not docs:
            # If no document markers found, treat entire file as one document
            docs = [content]
            
        # Find first non-empty document that parses as an ArgoCD Application
        data = None
        remaining_docs = []
        app_index = -1
        
        for i, doc in enumerate(docs):
            if not doc.strip():
                continue
                
            parsed = yaml.safe_load(doc)
            if not parsed:
                continue
                
            if (
                isinstance(parsed, dict) 
                and parsed.get('kind') == 'Application'
                and parsed.get('apiVersion', '').startswith('argoproj.io/')
            ):
                data = parsed
                app_index = i
                break
            
        if not data:
            return None
            
        # Store all other documents in their original order
        remaining_docs = []
        for i, doc in enumerate(docs):
            if i == app_index:
                continue
            if doc.strip():  # Skip empty documents
                remaining_docs.append(doc)
            
        if remaining_docs:
            data['__additional_resources'] = remaining_docs
            
        return data
    except Exception as e:
        rprint(f"[red]Error loading {file_path}: {e}[/red]")
        return None


def list_all_apps(verbose: bool = False) -> list[ArgoApp]:
    """List all ArgoApps from the APPS_DIRS"""
    apps = []
    for apps_dir in APPS_DIRS:
        app_dir = Path(apps_dir)
        if not app_dir.exists():
            continue
        
        for yaml_file in app_dir.glob("*.yaml"):
            data = load_yaml_file(yaml_file)
            if data is not None:
                try:
                    app = ArgoApp(yaml_file, data, verbose=verbose)
                    apps.append(app)
                except Exception as e:
                    rprint(f"[yellow]Warning: Failed to parse {yaml_file}: {e}[/yellow]")
    
    return apps


def list_all_helm_apps(verbose: bool = False) -> list[ArgoApp]:
    """Filter all ArgoApps to only those that use helm"""
    apps = list_all_apps(verbose=verbose)
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


@dataclass
class VersionCheck:
    """Result of a version check"""
    app: ArgoApp
    success: bool
    error: Optional[str] = None


def check_version(app: ArgoApp) -> VersionCheck:
    """Check version for a single app"""
    try:
        if not app.is_helm:
            return VersionCheck(app, True)
        
        # This will trigger the version check
        _ = app.latest_version
        return VersionCheck(app, True)
    except Exception as e:
        return VersionCheck(app, False, str(e))


class VersionChecker:
    """Manages parallel version checking with progress display"""
    def __init__(self, verbose: bool = False, show_progress: bool = True):
        self.verbose = verbose
        self.show_progress = show_progress
        self.completed = 0
        self.total = 0
        self._lock = threading.Lock()
    
    def increment(self) -> None:
        """Increment completed count"""
        with self._lock:
            self.completed += 1
    
    def check_version(self, app: ArgoApp) -> VersionCheck:
        """Check version for a single app"""
        try:
            if not app.is_helm:
                return VersionCheck(app, True)
            
            # This will trigger the version check
            _ = app.latest_version
            result = VersionCheck(app, True)
        except Exception as e:
            result = VersionCheck(app, False, str(e))
        
        self.increment()
        return result
    
    def check_versions_parallel(self, apps: list[ArgoApp], max_workers: int = 4) -> list[VersionCheck]:
        """Check versions for multiple apps in parallel with progress display"""
        self.total = len(apps)
        self.completed = 0
        results = []
        
        # Create progress display if enabled
        if self.show_progress:
            progress = Panel(
                Align.center(
                    f"Checking versions [0/{self.total}]",
                    vertical="middle"
                ),
                title="[bold blue]Progress",
            )
            live_context = Live(progress, console=console, refresh_per_second=10)
        else:
            live_context = nullcontext()
            progress = None
        
        with live_context:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_app = {
                    executor.submit(self.check_version, app): app 
                    for app in apps
                }
                
                for future in as_completed(future_to_app):
                    result = future.result()
                    if not result.success and self.verbose:
                        app = future.result().app
                        rprint(f"[yellow]Warning: Failed to check version for {app.name}: {result.error}[/yellow]")
                    results.append(result)
                    
                    # Update progress if enabled
                    if self.show_progress and progress:
                        progress.renderable = Align.center(
                            f"Checking versions [{self.completed}/{self.total}]",
                            vertical="middle"
                        )
        
        return results


@app.command()
def list(
    helm: bool = typer.Option(
        False,
        "--helm",
        help="Only show Helm-based applications",
    ),
    parallel: bool = typer.Option(
        True,
        "--parallel/--no-parallel",
        help="Check versions in parallel",
    ),
    workers: int = typer.Option(
        4,
        "--workers",
        help="Number of parallel workers",
        min=1,
        max=8,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show detailed progress",
    ),
    progress: bool = typer.Option(
        True,
        "--progress/--no-progress",
        help="Show progress bars",
    ),
):
    """List all ArgoCD applications with their current versions and update status.
    
    This command will:
    1. Find all ArgoCD application files in the configured directories
    2. Parse their current versions and source information
    3. For Helm charts, check if newer versions are available
    4. Display a table with app details and update status
    
    The status column shows:
    - : Up to date
    - : Update available
    - ? : Version check failed
    
    Args:
        helm: Only show Helm-based applications
        parallel: Check versions in parallel
        workers: Number of parallel workers (1-8)
        verbose: Show detailed progress
        progress: Show progress bars
    """
    apps = list_all_helm_apps(verbose=verbose) if helm else list_all_apps(verbose=verbose)
    
    # Check versions
    if parallel and apps:
        checker = VersionChecker(verbose=verbose, show_progress=progress)
        results = checker.check_versions_parallel(apps, workers)
    
    # Create table
    table = Table(title="Helm-based Argo CD Applications" if helm else "Argo CD Applications")
    table.add_column("Name")
    table.add_column("Namespace")
    table.add_column("Type")
    table.add_column("Chart")
    table.add_column("Current")
    table.add_column("Latest")
    table.add_column("Status", justify="center")
    
    for app in apps:
        # Determine status
        status = "[yellow]?[/yellow]"
        if app.is_helm:
            if app.latest_version:
                status = "[yellow]![/yellow]" if app.needs_update else "[green]✓[/green]"
            current_ver = app.target_revision
            latest_ver = app.latest_version or "Unknown"
        else:
            current_ver = app.target_revision if app.path else "N/A"
            latest_ver = "N/A"
            status = " "
        
        table.add_row(
            app.name,
            app.namespace,
            "Helm" if app.is_helm else "Git",
            app.chart or app.path or "",
            current_ver or "",
            latest_ver,
            status,
        )
    
    console.print(table)


@app.command()
def check(
    helm: bool = typer.Option(
        True,
        "--helm/--no-helm",
        help="Only check Helm charts",
    ),
    parallel: bool = typer.Option(
        True,
        "--parallel/--no-parallel",
        help="Check versions in parallel",
    ),
    workers: int = typer.Option(
        4,
        "--workers",
        help="Number of parallel workers",
        min=1,
        max=8,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show detailed progress",
    ),
    progress: bool = typer.Option(
        True,
        "--progress/--no-progress",
        help="Show progress bars",
    ),
):
    """Check if any ArgoCD applications need updates.
    
    This command will:
    1. Find all ArgoCD application files in the configured directories
    2. Check for available updates
    3. Show a table of current and latest versions
    4. Return exit code 1 if any updates are needed
    
    Examples:
        # Check all Helm apps for updates
        update_helm_apps.py check
        
        # Check all apps (including Git sources)
        update_helm_apps.py check --no-helm
        
        # Check with verbose output
        update_helm_apps.py check --verbose
    
    Args:
        helm: Only check Helm charts
        parallel: Check versions in parallel
        workers: Number of parallel workers (1-8)
        verbose: Show detailed progress
        progress: Show progress bars
    """
    apps = list_all_helm_apps(verbose=verbose) if helm else list_all_apps(verbose=verbose)
    
    # Check versions
    if parallel and apps:
        checker = VersionChecker(verbose=verbose, show_progress=progress)
        results = checker.check_versions_parallel(apps, workers)
    
    # Create table
    table = Table(title="Helm-based Argo CD Applications" if helm else "Argo CD Applications")
    table.add_column("Name")
    table.add_column("Namespace")
    table.add_column("Type")
    table.add_column("Chart")
    table.add_column("Current")
    table.add_column("Latest")
    table.add_column("Status", justify="center")
    
    updates_needed = []
    for app in apps:
        # Determine status
        status = "[yellow]?[/yellow]"
        if app.is_helm:
            if app.latest_version:
                needs_update = app.needs_update
                status = "[yellow]![/yellow]" if needs_update else "[green]✓[/green]"
                if needs_update:
                    updates_needed.append(app)
            current_ver = app.target_revision
            latest_ver = app.latest_version or "Unknown"
        else:
            current_ver = app.target_revision if app.path else "N/A"
            latest_ver = "N/A"
            status = " "
        
        table.add_row(
            app.name,
            app.namespace,
            "Helm" if app.is_helm else "Git",
            app.chart or app.path or "",
            current_ver or "",
            latest_ver,
            status,
        )
    
    console.print(table)
    console.print()
    
    if updates_needed:
        rprint("[yellow]Updates are available for the following apps:[/yellow]")
        for app in updates_needed:
            rprint(f"  - {app.name}: {app.target_revision} -> {app.latest_version}")
        rprint("\nTo apply updates, run:")
        rprint("  [blue]update_helm_apps.py update --no-dry-run --all[/blue]")
        raise typer.Exit(code=1)
    else:
        rprint("[green]All apps are up to date![/green]")
        raise typer.Exit(code=0)


@app.command()
def update(
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--no-dry-run",
        help="Show what would change without making changes",
    ),
    helm: bool = typer.Option(
        True,
        "--helm/--no-helm",
        help="Only update Helm charts",
    ),
    all: bool = typer.Option(
        False,
        "--all",
        help="Update all apps that need updates",
    ),
    app_name: str = typer.Option(
        None,
        "--app-name",
        help="Update a specific app by name",
    ),
    parallel: bool = typer.Option(
        True,
        "--parallel/--no-parallel",
        help="Check versions in parallel",
    ),
    workers: int = typer.Option(
        4,
        "--workers",
        help="Number of parallel workers",
        min=1,
        max=8,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show detailed progress",
    ),
    progress: bool = typer.Option(
        True,
        "--progress/--no-progress",
        help="Show progress bars",
    ),
):
    """Update ArgoCD application versions to their latest available versions.
    
    This command will:
    1. Check for available updates for your applications
    2. Verify that target files have no uncommitted changes
    3. Show a preview of all changes that will be made
    4. Update the version numbers in the YAML files
    5. Stage the modified files for commit
    
    The update process:
    1. First checks git status to prevent overwriting uncommitted changes
    2. Shows a table of all available updates
    3. In dry-run mode, shows exact file changes that would be made
    4. Without dry-run, applies changes and stages modified files
    
    Examples:
        # Show available updates
        update_helm_apps.py update
        
        # Update all apps that have updates available
        update_helm_apps.py update --no-dry-run --all
        
        # Update a specific app
        update_helm_apps.py update --no-dry-run --app-name sealed-secrets
    
    Args:
        dry_run: Show what would change without making changes
        helm: Only update Helm charts
        all: Update all apps that need updates
        app_name: Update a specific app by name
        parallel: Check versions in parallel
        workers: Number of parallel workers (1-8)
        verbose: Show detailed progress
        progress: Show progress bars
    """
    apps = list_all_helm_apps(verbose=verbose) if helm else list_all_apps(verbose=verbose)
    
    # Filter to specific app if requested
    if app_name:
        apps = [app for app in apps if app.name == app_name]
        if not apps:
            rprint(f"[red]Error: No app found with name {app_name}[/red]")
            return
    
    # Check versions in parallel
    if parallel and apps:
        checker = VersionChecker(verbose=verbose, show_progress=progress)
        results = checker.check_versions_parallel(apps, workers)
    
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
