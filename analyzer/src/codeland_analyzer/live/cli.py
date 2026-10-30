"""codeland-live: serve | install-hooks | uninstall-hooks | simulate."""

import argparse
from pathlib import Path

from codeland_analyzer.live import DEFAULT_PORT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="codeland-live", description="Live agent activity for the Codeland renderer."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="run the event server")
    serve.add_argument("repo", type=Path, help="repository the agents work in")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--history", type=int, default=500, help="events replayed to new clients")

    install = commands.add_parser(
        "install-hooks", help="add forwarding hooks to <repo>/.claude/settings.local.json"
    )
    install.add_argument("repo", type=Path)
    install.add_argument("--port", type=int, default=DEFAULT_PORT)

    uninstall = commands.add_parser("uninstall-hooks", help="remove the forwarding hooks")
    uninstall.add_argument("repo", type=Path)

    simulate = commands.add_parser("simulate", help="send fake agent activity to a running server")
    simulate.add_argument("repo", type=Path)
    simulate.add_argument("--city", type=Path, required=True, help="city model of the repo")
    simulate.add_argument("--port", type=int, default=DEFAULT_PORT)
    simulate.add_argument("--agents", type=int, default=2)
    simulate.add_argument("--steps", type=int, default=30)
    simulate.add_argument("--delay", type=float, default=0.8, help="seconds per action")

    args = parser.parse_args(argv)
    if args.command == "serve":
        from codeland_analyzer.live.server import serve as run_server

        run_server(args.repo, args.port, args.history)
    elif args.command == "install-hooks":
        from codeland_analyzer.live.hooks import install as install_hooks

        print(f"hooks installed in {install_hooks(args.repo, args.port)}")
    elif args.command == "uninstall-hooks":
        from codeland_analyzer.live.hooks import uninstall as uninstall_hooks

        print(f"hooks removed from {uninstall_hooks(args.repo)}")
    else:
        from codeland_analyzer.live.simulate import simulate as run_simulation

        run_simulation(
            args.repo,
            args.city,
            args.port,
            agents=args.agents,
            steps=args.steps,
            delay=args.delay,
        )
    return 0
