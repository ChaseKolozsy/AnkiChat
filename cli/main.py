#!/usr/bin/env python3
"""
AnkiChat CLI - Command-line interface for studying Anki cards

Main entry point with Click commands.
"""

import sys
import logging
import click
from rich.console import Console

from cli.server import ensure_server_running
from cli.client import AnkiChatAPIClient
from cli.session import InteractiveStudySession
from cli.display import display_deck_table, display_stats

# Set up logging
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

console = Console()


@click.group(invoke_without_command=True)
@click.pass_context
@click.option(
    '--host',
    default='localhost',
    envvar='ANKICHAT_HOST',
    help='API server host (default: localhost)'
)
@click.option(
    '--port',
    default=8888,
    type=int,
    envvar='ANKICHAT_PORT',
    help='API server port (default: 8888)'
)
@click.option(
    '--verbose', '-v',
    is_flag=True,
    help='Enable verbose logging'
)
def cli(ctx, host, port, verbose):
    """
    AnkiChat CLI - Study Anki cards in your terminal

    Run without arguments to start an interactive study session.

    \b
    Examples:
        ankichat-cli                    # Start interactive study
        ankichat-cli study --deck 5     # Start specific deck
        ankichat-cli sync               # Quick sync with AnkiWeb
        ankichat-cli stats              # Show deck statistics
    """
    # Set up logging level
    if verbose:
        logging.getLogger('cli').setLevel(logging.DEBUG)
        logging.getLogger().setLevel(logging.INFO)

    # Store in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj['HOST'] = host
    ctx.obj['PORT'] = port
    ctx.obj['VERBOSE'] = verbose

    # If no subcommand, default to interactive study
    if ctx.invoked_subcommand is None:
        ctx.invoke(study)


@cli.command()
@click.pass_context
@click.option(
    '--deck',
    type=int,
    help='Deck ID to study (skips deck selection)'
)
def study(ctx, deck):
    """Start interactive study session (default command)"""
    host = ctx.obj['HOST']
    port = ctx.obj['PORT']

    try:
        # Ensure server is running
        console.print("🚀 [bold]Starting AnkiChat CLI...[/bold]")
        server_url = ensure_server_running(host, port)
        console.print(f"✅ Connected to API server at {server_url}\n")

        # Create API client
        api = AnkiChatAPIClient(server_url)

        # Start interactive session
        session = InteractiveStudySession(api, console)
        session.run(deck_id=deck)

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        if ctx.obj['VERBOSE']:
            raise
        sys.exit(1)


@cli.command()
@click.pass_context
@click.option('--username', '-u', help='AnkiWeb username')
@click.option('--password', '-p', help='AnkiWeb password (not recommended)')
@click.option('--upload', is_flag=True, help='Upload changes to AnkiWeb')
def sync(ctx, username, password, upload):
    """Sync with AnkiWeb (one-off command)"""
    host = ctx.obj['HOST']
    port = ctx.obj['PORT']

    try:
        console.print("🔄 [bold]Syncing with AnkiWeb...[/bold]")

        # Ensure server is running
        server_url = ensure_server_running(host, port)

        # Create API client
        api = AnkiChatAPIClient(server_url)

        # Get credentials if not provided
        if not username:
            username = click.prompt('Username')
        if not password:
            password = click.prompt('Password', hide_input=True)

        # Perform sync
        result = api.login_and_sync(
            profile_name=username,
            username=username,
            password=password,
            upload=upload
        )

        if result.get('success'):
            console.print("✅ [green]Sync complete![/green]")
        else:
            error_msg = result.get('error', 'Unknown error')
            console.print(f"❌ [red]Sync failed: {error_msg}[/red]")
            sys.exit(1)

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if ctx.obj['VERBOSE']:
            raise
        sys.exit(1)


@cli.command()
@click.pass_context
@click.option('--username', '-u', help='AnkiWeb username')
def stats(ctx, username):
    """Show deck statistics"""
    host = ctx.obj['HOST']
    port = ctx.obj['PORT']

    try:
        # Ensure server is running
        server_url = ensure_server_running(host, port)

        # Create API client
        api = AnkiChatAPIClient(server_url)

        # Get username if not provided
        if not username:
            username = click.prompt('Username')

        # Get decks
        console.print(f"📊 [bold]Deck Statistics for {username}[/bold]\n")
        decks = api.get_decks(username)

        if not decks:
            console.print("[yellow]No decks found[/yellow]")
            return

        # Fetch and display counts for each deck
        for deck in decks:
            counts = api.get_deck_counts(deck['id'], username)
            deck.update(counts)

        display_deck_table(console, decks)

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if ctx.obj['VERBOSE']:
            raise
        sys.exit(1)


@cli.command()
@click.pass_context
@click.option('--username', '-u', help='AnkiWeb username')
def decks(ctx, username):
    """List available decks"""
    host = ctx.obj['HOST']
    port = ctx.obj['PORT']

    try:
        # Ensure server is running
        server_url = ensure_server_running(host, port)

        # Create API client
        api = AnkiChatAPIClient(server_url)

        # Get username if not provided
        if not username:
            username = click.prompt('Username')

        # Get and display decks
        console.print(f"📚 [bold]Decks for {username}[/bold]\n")
        deck_list = api.get_decks(username)

        if not deck_list:
            console.print("[yellow]No decks found[/yellow]")
            return

        display_deck_table(console, deck_list)

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if ctx.obj['VERBOSE']:
            raise
        sys.exit(1)


@cli.command()
@click.pass_context
def version(ctx):
    """Show version information"""
    from cli import __version__
    console.print(f"AnkiChat CLI v{__version__}")


if __name__ == '__main__':
    cli()
