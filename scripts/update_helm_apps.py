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
import json

import typer

app = typer.Typer()
console = Console()

# Use ruamel.yaml for safer YAML parsing
yaml = YAML(typ='safe')
yaml.default_flow_style = False

APPS_DIRS = [
    "argo-apps/core-apps",
    "argo-apps/apps",
    "argo-apps/fokais",
]


class ArgoApp:
    """Simple class to hold Argo CD application info"""
    def __init__(self, file: Path, data: dict):
        self.file = file
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
def update(dry_run: bool = False, helm: bool = False):
    """Update helm chart versions"""
    apps = list_all_helm_apps()
    for app in apps:
        if app.needs_update:
            rprint(f"Would update {app.name} from {app.target_revision} to {app.latest_version}")


if __name__ == "__main__":
    app()
