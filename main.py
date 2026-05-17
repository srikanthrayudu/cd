from pathlib import Path

from src.pipeline import run_pipeline


def main() -> None:
    run_pipeline(Path.cwd(), gen_count=20, mut_per_file=5, backend="template", model="gpt-4o-mini")


if __name__ == "__main__":
    main()
