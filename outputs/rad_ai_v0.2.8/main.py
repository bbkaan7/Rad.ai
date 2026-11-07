"""Rad.ai 0.2.8: CustomTkinter UI with an independent asyncio worker."""

import argparse


def main():
    parser = argparse.ArgumentParser(description="Rad.ai")
    parser.add_argument("--version", action="version", version="0.2.8")
    parser.add_argument("--headless", action="store_true", help="Run without the control panel; sign in inside the Android apps first.")
    parser.add_argument("--auto-reply", action="store_true", help="Enable replies when running headless.")
    args=parser.parse_args()
    if args.headless:
        import asyncio
        from rad.service import run
        try:
            asyncio.run(run(args.auto_reply))
        except KeyboardInterrupt:
            pass
        return
    from rad.gui import run
    run()


if __name__ == "__main__":
    main()
