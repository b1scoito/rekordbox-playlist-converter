"""Typer CLI: `rekordbox-converter` commands.

Three commands: `models` (list deck capabilities), `list` (enumerate
playlists in a rekordbox XML), `convert` (run the actual conversion). The
convert command orchestrates everything in `converter.py`; this module owns
only argument plumbing and user-facing rendering.
"""

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from _console import console
from converter import RekordboxPlaylistConverter
from models import CDJ_MODELS, get_recommended_format_for_cdj

app = typer.Typer(
    name="rekordbox-converter",
    help=(
        "Convert Rekordbox playlists with automatic format selection "
        "for Pioneer DJ CDJ/XDJ equipment"
    ),
    add_completion=False,
)


def render_cdj_models_table() -> None:
    """Print all supported CDJ/XDJ models with their format capabilities."""
    console.print("\n[bold cyan]Supported Pioneer DJ / AlphaTheta CDJ/XDJ Models[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Model", style="cyan", width=15)
    table.add_column("Year", justify="center", width=6)
    table.add_column("Recommended", style="green", width=12)
    table.add_column("Max Quality", width=15)
    table.add_column("Notes", width=30)

    # Newest first, then alphabetical within a year.
    for model, info in sorted(CDJ_MODELS.items(), key=lambda x: (-x[1]["year"], x[0])):
        recommended = info["recommended"].upper()
        max_qual = info["max_quality"].get(info["recommended"], "320kbps")
        notes = info.get("notes", "")
        table.add_row(model, str(info["year"]), recommended, max_qual, notes)

    console.print(table)
    console.print("\n[bold yellow]Why these recommendations?[/bold yellow]")
    console.print("  [green]FLAC[/green]: Lossless, excellent tag support, no compatibility issues")
    console.print(
        "  [green]MP3 320kbps[/green]: Universal support, no WAV/AIFF compatibility issues"
    )
    console.print("  [red]WAV/AIFF avoided[/red]: Known WAV_EXTENSIBLE metadata issues on CDJs\n")


@app.command(name="models")
def models_cmd() -> None:
    """List all supported CDJ/XDJ models with format recommendations."""
    render_cdj_models_table()


@app.command(name="list")
def list_cmd(
    xml_file: Annotated[Path, typer.Argument(help="Path to Rekordbox XML file", exists=True)],
) -> None:
    """List all playlists in a Rekordbox XML file."""
    try:
        converter = RekordboxPlaylistConverter(str(xml_file), "mp3")
        converter.load_xml()
        console.print("\n[bold cyan]Available playlists:[/bold cyan]")
        console.print("-" * 60)
        for path, _node, entries in converter.list_playlists():
            console.print(f"  {path} [dim]({entries} tracks)[/dim]")
        console.print()
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1) from e


@app.command(name="convert")
def convert_cmd(
    xml_file: Annotated[Path, typer.Argument(help="Path to Rekordbox XML file", exists=True)],
    playlist: Annotated[str, typer.Option("-p", "--playlist", help="Name of playlist to convert")],
    output: Annotated[
        Path, typer.Option("-o", "--output", help="Output directory for converted files")
    ],
    cdj_model: Annotated[
        str | None,
        typer.Option(
            "--cdj-model",
            help="Your CDJ/XDJ model (e.g., XDJ-RX2, CDJ-3000) - auto-selects best format",
        ),
    ] = None,
    format: Annotated[
        str | None,
        typer.Option(
            "-f",
            "--format",
            help=(
                "Output format (mp3, flac, aiff). If not specified, "
                "use --cdj-model for auto-selection"
            ),
        ),
    ] = None,
    output_xml: Annotated[
        Path | None,
        typer.Option(
            "--output-xml",
            help="Path for standalone XML file (default: saved in output directory)",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Probe and print the conversion plan without writing any files",
        ),
    ] = False,
    jobs: Annotated[
        int | None,
        typer.Option(
            "-j",
            "--jobs",
            help="Parallel ffmpeg workers (default: cpu_count; 1 disables parallelism)",
            min=1,
        ),
    ] = None,
    manifest: Annotated[
        Path | None,
        typer.Option(
            "--manifest",
            help=(
                "Path for the JSON conversion manifest "
                "(default: <output>/manifest.json; '-' disables)"
            ),
        ),
    ] = None,
) -> None:
    """Convert a Rekordbox playlist to MP3/FLAC/AIFF format.

    Creates a NEW standalone XML file that can be safely imported into
    Rekordbox without modifying your original library. Converted tracks
    get unique IDs starting from 1,000,000 to prevent collisions.
    """
    try:
        # Validate --cdj-model up front so a typo can't silently skip the
        # quality caps when --format is also provided.
        if cdj_model:
            try:
                recommended_format, reason = get_recommended_format_for_cdj(cdj_model)
            except ValueError as e:
                console.print(f"[bold red]Error:[/bold red] {e}")
                raise typer.Exit(code=1) from e
        else:
            recommended_format, reason = (None, None)

        output_format = "mp3"  # default
        if format:
            if format.lower() not in ("mp3", "flac", "aiff"):
                console.print(
                    f"[bold red]Error:[/bold red] Invalid format '{format}'. "
                    "Choose from: mp3, flac, aiff"
                )
                raise typer.Exit(code=1)
            output_format = format.lower()
        elif cdj_model and recommended_format:
            output_format = recommended_format
            console.print(f"\n[bold]CDJ Model:[/bold] {cdj_model.upper()}")
            console.print(
                f"[bold]Recommended format:[/bold] [green]{output_format.upper()}[/green]"
            )
            console.print(f"  {reason}\n")

        converter = RekordboxPlaylistConverter(str(xml_file), output_format, cdj_model=cdj_model)
        converter.load_xml()

        success, playlist_name, converted_tracks, results = converter.convert_playlist(
            playlist, str(output), dry_run=dry_run, jobs=jobs
        )

        if dry_run:
            # Plan table already printed by convert_playlist; nothing else to write.
            return

        if success and playlist_name:
            converter.create_standalone_xml(playlist_name, converted_tracks)
            if output_xml:
                output_xml_path = output_xml
            else:
                safe_name = converter.sanitize_filename(playlist_name)
                output_xml_path = output / f"{safe_name}.xml"
            converter.save_standalone_xml(str(output_xml_path))

            # Manifest: defaults to <output>/manifest.json; '-' disables.
            if manifest is None:
                manifest_path: Path | None = output / "manifest.json"
            elif str(manifest) == "-":
                manifest_path = None
            else:
                manifest_path = manifest
            if manifest_path is not None:
                converter.write_manifest(manifest_path, playlist_name, results)
                console.print(f"  [cyan]Manifest:[/cyan] {manifest_path}")

            console.print("\n" + "=" * 60)
            console.print("[bold green]Conversion complete[/bold green]")
            console.print(f"  [cyan]Converted files:[/cyan] {output}")
            console.print(f"  [cyan]Standalone XML:[/cyan] {output_xml_path}")
            console.print("  [yellow]Original XML:[/yellow] NOT MODIFIED")
        else:
            console.print("[bold red]Error:[/bold red] Conversion failed")
            raise typer.Exit(code=1)

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        import traceback

        traceback.print_exc()
        raise typer.Exit(code=1) from e
