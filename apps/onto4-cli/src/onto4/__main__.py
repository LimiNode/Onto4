"""Allow ``python -m onto4`` to invoke the CLI."""

from .cli.main import main


if __name__ == "__main__":
    raise SystemExit(main())
