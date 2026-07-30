#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "typer",
#     "sqlite-utils",
#     "rich",
# ]
# ///

import atexit
import datetime
import fcntl
import json
import os
import sys
from pathlib import Path
import re
from rich import print
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
import signal
import socket
import sqlite3
import sqlite_utils
import subprocess
import typer


app = typer.Typer()
DB_PATH = Path(os.environ.get("DB_PATH", "/var/mnt/main/media/media_inventory.db"))
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", "/var/mnt/main/media/media"))
TRANSCODED_ROOT = Path(
    os.environ.get("TRANSCODED_ROOT", "/var/mnt/main/media/transcoded")
)
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"}
SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa", ".sub"}

# Global to track files being processed
current_transcode = None
stopping = False


def cleanup_transcode(signum=None, frame=None):
    """Clean up any unfinished transcoding files and exit on signal."""
    global current_transcode, stopping
    
    if signum in (signal.SIGINT, signal.SIGTERM):
        stopping = True
        print("\n[yellow]Stopping after current transcode (if any)...[/yellow]")
    
    if current_transcode and current_transcode.exists():
        print(f"\nCleaning up unfinished transcode: {current_transcode}")
        current_transcode.unlink()
        
    if signum in (signal.SIGINT, signal.SIGTERM):
        sys.exit(1)


# Register cleanup for normal exit and signals
atexit.register(cleanup_transcode)
signal.signal(signal.SIGINT, cleanup_transcode)
signal.signal(signal.SIGTERM, cleanup_transcode)


def try_lock_file(lock_file: Path) -> bool:
    """Try to acquire a lock file for transcoding."""
    try:
        # Ensure parent directory exists
        lock_file.parent.mkdir(parents=True, exist_ok=True)

        # Try to create or open the lock file
        with open(lock_file, "a") as f:
            try:
                # Try to acquire an exclusive lock
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

                # Write process info to lock file
                f.truncate(0)
                f.write(
                    f"Locked by {socket.gethostname()} at {datetime.datetime.now().isoformat()}\n"
                )
                f.write(f"PID: {os.getpid()}\n")
                f.flush()

                return True
            except (IOError, OSError) as e:
                print(f"Couldn't acquire lock: {e}")
                return False
    except (IOError, OSError) as e:
        print(f"Error with lock file {lock_file}: {e}")
        return False


def is_being_transcoded(output_path: Path) -> bool:
    """Check if a file is currently being transcoded by checking lock file."""
    lock_file = output_path.with_suffix(output_path.suffix + ".lock")

    if not lock_file.exists():
        return False

    try:
        # Try to acquire lock to check if it's stale
        with open(lock_file, "r+") as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                # If we got the lock, the file is stale
                try:
                    lock_file.unlink()
                except OSError:
                    pass
                return False
            except (IOError, OSError):
                # Lock is held by another process
                return True
    except (IOError, OSError) as e:
        print(f"Error checking lock file {lock_file}: {e}")
        return False

    return True


def get_media_info(file_path: Path) -> dict | None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError:
        print(f"[red]Error reading file:[/red] {file_path}")
        return None


def find_transcoded_version(original_path: Path) -> Path | None:
    """Find the transcoded version of a file if it exists."""
    try:
        relative_path = get_relative_path(original_path, MEDIA_ROOT)
        transcoded_path = TRANSCODED_ROOT / relative_path
        transcoded_path = transcoded_path.with_suffix(".mp4")
        return transcoded_path if transcoded_path.exists() else None
    except Exception:
        return None


def get_relative_path(path: Path, root: Path) -> Path:
    """Get the relative path from root."""
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def find_external_subtitles(video_path: Path) -> list[Path]:
    """Find external subtitle files for a given video."""
    subtitles = []
    base_path = video_path.with_suffix("")
    for ext in SUBTITLE_EXTENSIONS:
        subtitle_path = base_path.with_suffix(ext)
        if subtitle_path.exists():
            subtitles.append(subtitle_path)
    return subtitles


def get_output_path(input_path: Path, preview: bool = False) -> Path:
    """Get the output path for a transcoded file."""
    # Get relative path from MEDIA_ROOT
    relative_path = input_path.relative_to(MEDIA_ROOT)
    
    # Strip any existing encoding info from filename
    base_name = input_path.stem
    base_name = re.sub(r"_(4k|1080p|720p|480p)_(h264|h265|hevc)", "", base_name)
    base_name = re.sub(r"_(Remux|WEBDL|HDTV|Bluray)", "", base_name)
    
    # Add appropriate suffix
    if preview:
        filename = f"{base_name}_preview.mp4"
    else:
        filename = f"{base_name}_1080p_h264.mp4"
    
    return TRANSCODED_ROOT / relative_path.parent / filename


def get_ffmpeg_command(input_path: Path, output_path: Path, preview: bool = False) -> str:
    """Generate FFmpeg command for transcoding."""
    external_subs = find_external_subtitles(input_path)

    # First get audio stream info
    probe_cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "a",
        str(input_path)
    ]
    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
    audio_info = json.loads(probe_result.stdout)

    cmd = ["ffmpeg", "-y"]  # Add -y to overwrite files

    if preview:
        # Use -to for exact end time
        cmd.extend([
            "-i", str(input_path),
            "-ss", "300",        # Start at 5 minutes
            "-to", "420",        # End at 7 minutes (5min + 2min = 420 seconds)
        ])
    else:
        cmd.extend(["-i", str(input_path)])

    # Add all subtitle files if they exist
    for sub in external_subs:
        cmd.extend(["-i", str(sub)])

    # Map all video streams
    cmd.extend(["-map", "0:v:0"])
    
    # Map all audio streams
    cmd.extend(["-map", "0:a?"])
    
    # Map all subtitle streams from input
    cmd.extend(["-map", "0:s?"])
    
    # Map subtitle files if present
    for i in range(len(external_subs)):
        cmd.extend(["-map", f"{i+1}:s?"])

    # Preserve chapters and metadata
    cmd.extend([
        "-map_chapters", "0",
        "-map_metadata", "0"
    ])

    # Video encoding parameters
    cmd.extend([
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-profile:v", "high",
        "-pix_fmt", "yuv420p",
        "-level:v", "4.1",
        "-vf", "scale=1920:1080:flags=lanczos,fps=fps=30",
    ])

    # Audio encoding parameters - handle each stream
    for i, stream in enumerate(audio_info.get('streams', [])):
        channels = int(stream.get('channels', 2))
        codec = stream.get('codec_name', '').lower()
        
        # For 5.1/7.1 audio use AC-3
        if channels > 2:
            if codec == 'ac3':
                cmd.extend([f"-c:a:{i}", "copy"])
            else:
                cmd.extend([
                    f"-c:a:{i}", "ac3",
                    f"-b:a:{i}", "448k",  # Standard AC-3 bitrate for 5.1
                    f"-ac:a:{i}", "6",    # Force to 5.1 for AC-3
                    "-strict", "2"         # Allow experimental codecs
                ])
        # For stereo audio use AAC
        else:
            if codec == 'aac':
                cmd.extend([f"-c:a:{i}", "copy"])
            else:
                cmd.extend([
                    f"-c:a:{i}", "aac",
                    f"-b:a:{i}", "192k",
                    f"-ac:a:{i}", "2",     # Force to stereo
                    "-strict", "2"         # Allow experimental codecs
                ])

    # Subtitle encoding
    cmd.extend(["-c:s", "mov_text"])

    # Add metadata
    cmd.extend([
        # Only add our custom metadata tags
        "-metadata:s:v:0", "encoding_tool=Jellyfin Optimized Transcode",
        "-metadata:s:v:0", "title=1080p 30fps H.264 Version",
        "-metadata:s:v:0", "comment=Optimized for direct play with AC-3/AAC audio",
        "-metadata:s:v:0", "description=1080p 30fps H.264 with AC-3 5.1/AAC Stereo",
        # Format specific options for MP4
        "-f", "mp4",
        "-movflags", "+faststart",  # Optimize for streaming playback
        "-threads", "0",
        str(output_path)
    ])

    return " ".join(f'"{arg}"' if " " in str(arg) else str(arg) for arg in cmd)


@app.command()
def scan(
    refresh: bool = typer.Option(
        False, "--refresh", help="Re-scan all files from scratch."
    ),
):
    db = sqlite_utils.Database(DB_PATH)

    # Create tables if they don't exist
    files_table = db["media_files"]
    files_table.create(
        {
            "path": str,
            "needs_transcode": bool,
            "has_transcoded": bool,
            "transcoded_path": str,
            "format": str,
            "video_codec": str,
            "video_profile": str,
            "video_level": str,
            "video_bit_depth": int,
            "video_resolution": str,
            "audio_codec": str,
            "audio_channels": int,
            "subtitle_format": str,
            "duration": float,
            "size": int,
        },
        pk="path",
        if_not_exists=True,
    )

    print("[bold cyan]Scanning for video files...[/bold cyan]")

    # Find all video files in both original and transcoded directories
    all_video_files = []
    for root in [MEDIA_ROOT, TRANSCODED_ROOT]:
        for file_root, _, files in os.walk(root):
            for name in files:
                if Path(name).suffix.lower() in VIDEO_EXTENSIONS:
                    all_video_files.append(Path(file_root) / name)

    with Progress(
        SpinnerColumn(),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        TextColumn("{task.description}"),
        transient=True,
    ) as progress:
        task = progress.add_task(
            "[green]Processing media files...", total=len(all_video_files)
        )

        for path in all_video_files:
            if not refresh:
                existing = list(files_table.rows_where("path = ?", [str(path)]))
                if existing:
                    progress.update(
                        task, advance=1, description=f"Skipping existing: {path.name}"
                    )
                    continue

            progress.update(task, description=f"Processing: {path.name}")

            info = get_media_info(path)
            if not info:
                progress.update(
                    task, advance=1, description=f"Failed to get info: {path.name}"
                )
                continue

            video_streams = [
                s for s in info.get("streams", []) if s.get("codec_type") == "video"
            ]
            audio_streams = [
                s for s in info.get("streams", []) if s.get("codec_type") == "audio"
            ]
            subtitle_streams = [
                s for s in info.get("streams", []) if s.get("codec_type") == "subtitle"
            ]

            format_name = info.get("format", {}).get("format_name", "")
            video_codec = (
                video_streams[0].get("codec_name", "") if video_streams else ""
            )
            video_profile = video_streams[0].get("profile", "") if video_streams else ""
            video_level = video_streams[0].get("level", "") if video_streams else ""
            video_bit_depth = (
                int(video_streams[0].get("bits_per_raw_sample", 8))
                if video_streams
                else 8
            )

            if video_streams:
                width = video_streams[0].get("width", 0)
                height = video_streams[0].get("height", 0)
                video_resolution = f"{width}x{height}"
            else:
                video_resolution = ""

            audio_codec = (
                audio_streams[0].get("codec_name", "") if audio_streams else ""
            )
            audio_channels = (
                int(audio_streams[0].get("channels", 0)) if audio_streams else 0
            )
            subtitle_format = (
                subtitle_streams[0].get("codec_name", "") if subtitle_streams else ""
            )
            duration = float(info.get("format", {}).get("duration", 0))
            size = int(info.get("format", {}).get("size", 0))

            # Check if this is an original or transcoded file
            is_transcoded = str(path).startswith(str(TRANSCODED_ROOT))

            if is_transcoded:
                # For transcoded files, find the original
                try:
                    relative_path = get_relative_path(path, TRANSCODED_ROOT)
                    original_path = MEDIA_ROOT / relative_path
                    original_path = (
                        original_path.parent / original_path.stem
                    )  # Remove .mp4 extension
                    # Try common extensions for original
                    for ext in VIDEO_EXTENSIONS:
                        test_path = original_path.with_suffix(ext)
                        if test_path.exists():
                            original_path = test_path
                            break
                except Exception:
                    original_path = None

                if original_path and original_path.exists():
                    # Update the original file's record
                    files_table.upsert(
                        {
                            "path": str(original_path),
                            "has_transcoded": True,
                            "transcoded_path": str(path),
                        },
                        pk="path",
                    )
            else:
                # For original files, check if a transcoded version exists
                transcoded_path = find_transcoded_version(path)

                # Determine if file needs transcoding
                needs_transcode = False
                if "matroska" in format_name:
                    needs_transcode = True
                if video_codec == "hevc" or (
                    video_codec == "h264" and video_bit_depth > 8
                ):
                    needs_transcode = True
                if video_level and float(video_level) > 41:
                    needs_transcode = True
                if audio_channels > 2:
                    needs_transcode = True
                if subtitle_format and subtitle_format not in ["subrip", "ass", "ssa"]:
                    if subtitle_format in [
                        "dvdsub",
                        "dvd_subtitle",
                        "hdmv_pgs_subtitle",
                    ]:
                        needs_transcode = True

                files_table.upsert(
                    {
                        "path": str(path),
                        "needs_transcode": needs_transcode,
                        "has_transcoded": bool(transcoded_path),
                        "transcoded_path": str(transcoded_path)
                        if transcoded_path
                        else "",
                        "format": format_name,
                        "video_codec": video_codec,
                        "video_profile": video_profile,
                        "video_level": video_level,
                        "video_bit_depth": video_bit_depth,
                        "video_resolution": video_resolution,
                        "audio_codec": audio_codec,
                        "audio_channels": audio_channels,
                        "subtitle_format": subtitle_format,
                        "duration": duration,
                        "size": size,
                    },
                    pk="path",
                )

            progress.update(task, advance=1)

    print("[bold green]Scan complete.[/bold green]")


@app.command()
def analyze():
    """Analyze the media library and show transcode status."""
    db = sqlite_utils.Database(DB_PATH)
    table = db["media_files"]

    # Only look at original files, not transcoded versions
    results = [
        r for r in table.rows if not str(r["path"]).startswith(str(TRANSCODED_ROOT))
    ]

    table_display = Table(title="Media File Analysis")
    table_display.add_column("Status", style="bold red")
    table_display.add_column("Path", style="cyan")
    table_display.add_column("Format", style="yellow")
    table_display.add_column("Video", style="green")
    table_display.add_column("Resolution", style="blue")
    table_display.add_column("Audio", style="magenta")
    table_display.add_column("Subtitles", style="red")

    # Sort results to show files needing transcoding first
    results.sort(key=lambda x: (not x["needs_transcode"], x["path"]))

    for row in results:
        video_info = f"{row['video_codec']} ({row['video_bit_depth']}-bit)"
        if row["video_level"]:
            video_info += f" L{row['video_level']}"

        if row["has_transcoded"]:
            status = "[blue]✓ Transcoded[/blue]"
        elif row["needs_transcode"]:
            status = "[red]⚠ Needs Transcode[/red]"
        else:
            status = "[green]✓ Direct Play[/green]"

        subtitle_info = row["subtitle_format"] or "none"
        if row["subtitle_format"] in ["dvdsub", "dvd_subtitle", "hdmv_pgs_subtitle"]:
            subtitle_info += " [red](timing risk)[/red]"

        table_display.add_row(
            status,
            row["path"],
            row["format"],
            video_info,
            row["video_resolution"],
            f"{row['audio_codec']} ({row['audio_channels']}ch)",
            subtitle_info,
        )

    print(table_display)

    # Print summary statistics
    total_files = len(results)
    needs_transcode = sum(1 for r in results if r["needs_transcode"])
    already_transcoded = sum(1 for r in results if r["has_transcoded"])
    direct_play = sum(1 for r in results if not r["needs_transcode"])

    print("\n[bold]Summary:[/bold]")
    print(f"Total files: {total_files}")
    print(
        f"Needs transcode: {needs_transcode} ({needs_transcode / total_files * 100:.1f}%)"
    )
    print(
        f"Already transcoded: {already_transcoded} ({already_transcoded / total_files * 100:.1f}%)"
    )
    print(f"Direct play ready: {direct_play} ({direct_play / total_files * 100:.1f}%)")


@app.command()
def status():
    """Show current transcoding status and progress."""
    db = sqlite_utils.Database(DB_PATH)

    # Get counts
    total_result = list(
        db.query("SELECT COUNT(*) as count FROM media_files WHERE needs_transcode = 1")
    )[0]
    total = total_result["count"]

    # Count completed files by looking in movies/shows subdirectories
    completed = 0
    if TRANSCODED_ROOT.exists():
        movies_dir = TRANSCODED_ROOT / "movies"
        shows_dir = TRANSCODED_ROOT / "shows"

        if movies_dir.exists():
            completed += len(list(movies_dir.rglob("*_1080p30_h264.mp4")))
        if shows_dir.exists():
            completed += len(list(shows_dir.rglob("*_1080p30_h264.mp4")))

    # Find active transcodes
    active = []
    for lock in TRANSCODED_ROOT.rglob("*.lock"):
        if lock.exists():  # Check again in case it was just removed
            try:
                with open(lock, "r") as f:
                    info = f.read().strip()
                    target = lock.with_suffix("")  # Remove .lock to get target file
                    active.append((target.name, info))
            except OSError:
                continue

    # Calculate remaining
    remaining = total - completed
    percent = (completed / total * 100) if total > 0 else 0

    # Print summary
    print("\n📊 Transcoding Progress")
    print("------------------------")
    print(f"Total files:     {total:>5}")
    print(f"Completed:       {completed:>5} ({percent:.1f}%)")
    print(f"Remaining:       {remaining:>5}")

    if active:
        print("\n🔄 Active Transcodes")
        print("------------------------")
        for file, info in active:
            print(f"\n{file}")
            print(f"{info}")


@app.command()
def generate_transcode_commands(
    output_script: bool = typer.Option(
        False, "--script", help="Output clean shell script without formatting"
    ),
):
    """Generate FFmpeg commands for files that need transcoding."""
    db = sqlite_utils.Database(DB_PATH)
    table = db["media_files"]
    results = list(table.rows_where("needs_transcode = 1 AND has_transcoded = 0"))

    if not results:
        if not output_script:
            print("[green]No files need transcoding![/green]")
        return

    if output_script:
        # Output clean shell script
        print("#!/bin/bash")
        print("# Generated by transcode_inventory.py")
        print("# Transcodes media files for optimal Jellyfin direct play")
        print("# Settings:")
        print("#  - H.264 High Profile Level 4.1")
        print("#  - CRF 18 (visually lossless)")
        print("#  - AAC audio (stereo)")
        print("#  - Subtitle conversion to SRT where needed")
        print()
        print("set -e  # Exit on error")
        print()
        print("# Setup progress tracking")
        print("start_time=$(date +%s)")
        print(f"total_files={len(results)}")
        print("current_file=1")
        print()
        print("transcode_file() {")
        print('    input_file="$1"')
        print('    temp_output="$2"')
        print('    final_output="$3"')
        print("    shift 3")
        print(
            '    echo "Starting file $current_file/$total_files: $(basename "$input_file")"'
        )
        print('    mkdir -p "$(dirname "$temp_output")"')
        print('    if ffmpeg -i "$input_file" "$@" "$temp_output"; then')
        print('        mv "$temp_output" "$final_output"')
        print("        elapsed=$(($(date +%s) - start_time))")
        print("        avg_time=$((elapsed / current_file))")
        print("        remaining=$(((total_files - current_file) * avg_time))")
        print('        echo "Completed $current_file/$total_files files"')
        print('        echo "Elapsed: $(date -d @$elapsed -u +%H:%M:%S)"')
        print('        echo "Average per file: $(date -d @$avg_time -u +%H:%M:%S)"')
        print('        echo "Estimated remaining: $(date -d @$remaining -u +%H:%M:%S)"')
        print("        echo")
        print("        ((current_file++))")
        print("        return 0")
        print("    else")
        print('        echo "Error transcoding: $input_file"')
        print("        return 1")
        print("    fi")
        print("}")
        print()
        print(f'echo "Creating output directory: {TRANSCODED_ROOT}"')
        print(f'mkdir -p "{TRANSCODED_ROOT}"')
        print()
        print(f'echo "Starting transcoding of {len(results)} files..."')
        print()
    else:
        print("[bold]FFmpeg Transcode Commands:[/bold]")
        print(f"Transcoded files will be stored in: {TRANSCODED_ROOT}\n")
        print(
            "These commands will transcode your files for optimal Jellyfin direct play while maintaining quality.\n"
        )
        print("[bold yellow]Setup:[/bold yellow]")
        print(f"mkdir -p {TRANSCODED_ROOT}")
        print()

    for row in results:
        input_path = Path(row["path"])
        output_path = get_output_path(input_path)

        if not output_script:
            print(f"[bold cyan]File:[/bold cyan] {input_path.name}")
            print("[bold green]Command:[/bold green]")

        # Create output directory
        print(f"mkdir -p {output_path.parent}")

        # Base command with high quality settings
        command = get_ffmpeg_command(input_path, output_path)

        # For script output, remove the comments after each option
        if output_script:
            command = command.split("#")[0].strip()
            # Clean up paths by removing newlines and extra spaces
            input_path_clean = str(input_path).replace("\n", " ").strip()
            output_path_clean = str(output_path).replace("\n", " ").strip()

            # Create parent directory
            print(f'mkdir -p "$(dirname "{output_path_clean}")"')

            # Call the transcode function with properly escaped arguments
            print(
                f'transcode_file "{input_path_clean}" "{output_path_clean}.transcoding" "{output_path_clean}" {command}'
            )
            print()
        else:
            print(command)
            print(f'mv "{output_path}.transcoding" "{output_path}"')
            print()

    if output_script:
        print('echo "\\nTranscoding complete!"')
        print("total_elapsed=$(($(date +%s) - start_time))")
        print('echo "Total time: $(date -d @$total_elapsed -u +%H:%M:%S)"')
        print(
            'echo "Average per file: $(date -d @$((total_elapsed / total_files)) -u +%H:%M:%S)"'
        )
    else:
        print("[bold yellow]Notes:[/bold yellow]")
        print(
            "1. Transcoded files will maintain the same directory structure in the new location"
        )
        print("2. Original files remain untouched")
        print("3. In Jellyfin, you can:")
        print("   a. Add both libraries but give transcoded versions higher priority")
        print("   b. Or only add the transcoded library for affected content")
        print("4. H.264 High Profile Level 4.1 ensures wide device compatibility")
        print("5. CRF 18 provides visually lossless quality")
        print("6. Audio is converted to stereo")
        print("7. Subtitles are converted to SRT when possible for better timing")

        print("\n[bold]To generate a clean shell script:[/bold]")
        print(
            "./scripts/transcode_inventory.py generate-transcode-commands --script > transcode_commands.sh"
        )
        print("chmod +x transcode_commands.sh")
        print("./transcode_commands.sh")


@app.command()
def transcode(
    preview: bool = typer.Option(
        False,
        "--preview",
        "-p",
        help="Create 2-minute preview starting 5 minutes in",
    ),
    max_concurrent: int = typer.Option(
        1, help="Maximum number of concurrent transcodes"
    ),
):
    """Transcode media files."""
    global current_transcode, stopping

    db = sqlite_utils.Database(DB_PATH)
    try:
        results = db.query("""
            SELECT * FROM media_files 
            WHERE needs_transcode = 1 
            ORDER BY path
        """)
        results = list(results)
    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            print(
                "❌ Database table not found. Please run 'scan' first to initialize the database."
            )
            raise typer.Exit(1)
        raise

    if not results:
        print("No files need transcoding!")
        return

    print(f"Found {len(results)} files to transcode")
    
    for row in results:
        if stopping:
            print("[yellow]Stopped by user request.[/yellow]")
            break
            
        input_path = Path(row["path"])
        output_path = get_output_path(input_path, preview)

        # Skip if being transcoded
        if not check_transcode_status(output_path):
            continue

        # Create output directory
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Try to acquire lock
        if not try_lock_file(output_path.with_suffix(output_path.suffix + ".lock")):
            print(f"[yellow]Skipping {output_path.name} - could not acquire lock[/yellow]")
            continue

        current_transcode = output_path.with_stem(f"{output_path.stem}.transcoding")
        command = get_ffmpeg_command(input_path, current_transcode, preview)

        try:
            print(f"\n[bold cyan]Transcoding:[/bold cyan] {input_path.name}")
            subprocess.run(command, shell=True, check=True)
            current_transcode.rename(output_path)
            print(f"[green]✓ Completed:[/green] {output_path.name}")
        except subprocess.CalledProcessError as e:
            print(f"[red]Error transcoding {input_path.name}:[/red] {e}")
            if current_transcode.exists():
                current_transcode.unlink()
        finally:
            current_transcode = None
            cleanup_transcode()


def check_transcode_status(output_path: Path) -> bool:
    """Check if a file is currently being transcoded or has a lock file.

    Returns:
        bool: True if file is safe to transcode, False if it's being worked on
    """
    # Check for transcoding file
    transcoding_path = output_path.with_stem(f"{output_path.stem}.transcoding")
    if transcoding_path.exists():
        print(f"[yellow]Skipping {output_path.name} - transcoding in progress[/yellow]")
        return False

    # Check for lock file
    lock_file = output_path.with_suffix(output_path.suffix + ".lock")
    if lock_file.exists():
        try:
            # Try to acquire lock to check if it's stale
            with open(lock_file, "r+") as f:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    # If we got the lock, the file is stale
                    lock_file.unlink()
                    return True
                except (IOError, OSError):
                    # Lock is held by another process
                    print(f"[yellow]Skipping {output_path.name} - locked by another process[/yellow]")
                    return False
        except (IOError, OSError) as e:
            print(f"[yellow]Warning: Error checking lock file {lock_file}: {e}[/yellow]")
            return False

    return True


@app.command()
def cleanup(
    preview_only: bool = typer.Option(
        False,
        "--preview-only",
        "-p",
        help="Only clean up preview files",
    )
) -> None:
    """Clean up stale transcode and lock files."""
    try:
        # Clean up transcoding files
        for f in Path(TRANSCODED_ROOT).rglob("*.transcoding"):
            try:
                print(f"Removing stale transcode: {f}")
                f.unlink(missing_ok=True)
            except Exception as e:
                print(f"Error removing {f}: {e}")

        # Clean up lock files
        for f in Path(TRANSCODED_ROOT).rglob("*.lock"):
            try:
                print(f"Removing stale lock: {f}")
                f.unlink(missing_ok=True)
            except Exception as e:
                print(f"Error removing {f}: {e}")

        # Clean up preview files if requested
        if preview_only:
            for pattern in ["*_preview*.mp4", "*_preview*.transcoding"]:
                for f in Path(TRANSCODED_ROOT).rglob(pattern):
                    try:
                        print(f"Removing preview file: {f}")
                        f.unlink(missing_ok=True)
                    except Exception as e:
                        print(f"Error removing {f}: {e}")
                    
    except Exception as e:
        print(f"Error during cleanup: {e}")


@app.command()
def transcode(
    preview: bool = typer.Option(
        False,
        "--preview",
        "-p",
        help="Create 2-minute preview starting 5 minutes in",
    ),
    output_script: bool = typer.Option(
        False, "--script", "-s", help="Output shell script instead of transcoding"
    ),
) -> None:
    """Transcode media files."""
    setup_environment()
    
    # Get files to transcode
    results = get_files_to_transcode()

    for row in results:
        input_path = Path(row["path"])
        output_path = get_output_path(input_path, preview)

        if not output_script:
            print(f"[bold cyan]File:[/bold cyan] {input_path.name}")
            print(f"[bold cyan]Output:[/bold cyan] {output_path}")

        print(f"mkdir -p {output_path.parent}")

        # Base command with high quality settings
        command = get_ffmpeg_command(input_path, output_path, preview)

        try:
            if preview:
                # For preview mode, we'll only keep the first segment
                # and rename it to remove the segment number
                process = subprocess.run(command.split(), check=True, capture_output=True, text=True)
                
                # Find the first segment and rename it
                segments = list(output_path.parent.glob(f"{output_path.stem}*.mp4"))
                if segments:
                    first_segment = segments[0]
                    final_name = first_segment.with_name(first_segment.name.replace("000", ""))
                    first_segment.rename(final_name)
                    
                    # Remove any additional segments
                    for segment in segments[1:]:
                        segment.unlink()
            else:
                # Normal transcode
                subprocess.run(command.split(), check=True)
                
        except subprocess.CalledProcessError as e:
            print(f"Error transcoding {input_path}: {e}")
            continue


if __name__ == "__main__":
    app()
