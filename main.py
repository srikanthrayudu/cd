import argparse
from pathlib import Path

from src.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the LLVM IR Differential Testing Pipeline")
    parser.add_argument("--gen-count", type=int, default=10, help="Number of files to generate")
    parser.add_argument("--mut-per-file", type=int, default=1, help="Number of mutations per file")
    parser.add_argument("--backend", type=str, default="template", choices=["template", "openai", "anthropic"], help="Generation backend to use")
    parser.add_argument("--model", type=str, default="gpt-4o-mini", help="LLM model name if using LLM backend")
    # Option A: run tests on a single file (default: test.ll) and save results
    parser.add_argument("--option-a", action="store_true", help="Run tests on a single file (Option A)")
    parser.add_argument("--option-a-file", type=str, default="test.ll", help="Path to the .ll file to test when using --option-a")

    args = parser.parse_args()
    
    if args.option_a:
        run_pipeline(
            Path.cwd(),
            gen_count=args.gen_count,
            mut_per_file=args.mut_per_file,
            backend=args.backend,
            model=args.model,
            test_file=Path(args.option_a_file),
        )
    else:
        run_pipeline(
            Path.cwd(),
            gen_count=args.gen_count,
            mut_per_file=args.mut_per_file,
            backend=args.backend,
            model=args.model
        )

if __name__ == "__main__":
    main()
