"""CLI entry point for Horizon."""

import argparse
import asyncio
import sys

from rich.console import Console

from .core.config_service import ConfigService
from .core.errors import ErrorCode, HorizonApiError
from .core.settings import load_environment_files
from .storage.manager import StorageManager
from .orchestrator import HorizonOrchestrator


console = Console()


def print_banner():
    """Print the application banner."""
    banner = r"""
[bold blue]
  _    _            _
 | |  | |          (_)
 | |__| | ___  _ __ _ ___  ___  _ __
 |  __  |/ _ \| '__| |_  / / _ \| '_ \
 | |  | | (_) | |  | |/ / | (_) | | | |
 |_|  |_|\___/|_|  |_/___| \___/|_| |_|
[/bold blue]
[cyan]  AI-Driven Information Aggregation System[/cyan]
    """
    console.print(banner)


def main():
    """Main CLI entry point."""
    print_banner()

    parser = argparse.ArgumentParser(description="Horizon - AI-Driven Information Aggregation System")
    parser.add_argument("--hours", type=int, help="Force fetch from last N hours")
    args = parser.parse_args()

    try:
        settings = load_environment_files()

        # Initialize storage manager
        storage = StorageManager(data_dir=str(settings.data_dir), config_path=settings.config_path)

        # Load configuration
        try:
            config = ConfigService(settings.config_path).get_config()
        except HorizonApiError as exc:
            if exc.error_code != ErrorCode.CONFIG_FILE_NOT_FOUND:
                raise
            console.print("[bold red]❌ Configuration file not found![/bold red]\n")
            console.print(
                "Run [bold cyan]uv run horizon-wizard[/bold cyan] to launch the interactive setup wizard,\n"
                f"or create [cyan]{settings.config_path}[/cyan] manually based on the template:\n"
            )
            print_config_template()
            sys.exit(1)
        except Exception as e:
            console.print(f"[bold red]❌ Error loading configuration: {e}[/bold red]")
            sys.exit(1)

        # Create and run orchestrator
        orchestrator = HorizonOrchestrator(config, storage)
        asyncio.run(orchestrator.run(force_hours=args.hours))

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[bold red]❌ Fatal error: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def print_config_template():
    """Print configuration template."""
    template = """
{
  "version": "1.0",
  "ai": {
    "provider": "anthropic",
    "model": "claude-sonnet-4.5-20250929",
    "api_key": "your_api_key_here",
    "temperature": 0.3,
    "max_tokens": 4096
  },
  "github_token": "your_github_token_here",
  "sources": {
    "github": [
      {
        "type": "user_events",
        "username": "torvalds",
        "enabled": true
      }
    ],
    "hackernews": {
      "enabled": true,
      "fetch_top_stories": 30,
      "min_score": 100
    },
    "rss": [
      {
        "name": "Example Blog",
        "url": "https://example.com/feed.xml",
        "enabled": true,
        "category": "software-engineering"
      }
    ]
  },
  "filtering": {
    "ai_score_threshold": 7.0,
    "time_window_hours": 24
  }
}

Save this as ~/.horizon/settings.json.
"""
    console.print(template)


if __name__ == "__main__":
    main()
