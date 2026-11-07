"""Rad.ai 0.1.12: CustomTkinter UI with an independent asyncio worker."""

import argparse


def main():
    from rad.diagnostics import install
    install()
    parser = argparse.ArgumentParser(description="Rad.ai")
    parser.add_argument("--version", action="version", version="0.1.12")
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
    try:main()
    except Exception as error:
        from rad.diagnostics import record
        record('application.startup',error)
        print('Rad.ai could not complete startup. See runtime/rad_error.log for diagnostics.')
        raise SystemExit(1)
