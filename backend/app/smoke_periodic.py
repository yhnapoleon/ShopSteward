"""B0-06 three-process wall-clock/SC01 acceptance; preserves B0-05 evidence."""

import argparse
import asyncio

from app.smoke_execution import DIRECTORY, run

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-restart", action="store_true")
    asyncio.run(
        run(
            parser.parse_args().verify_restart,
            output=DIRECTORY / "b0-06-periodic-smoke-result.json",
            automatic=True,
        )
    )
