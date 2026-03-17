# dev_runner.py — run the bot and restart automatically when .py files change.
# Usage: python dev_runner.py   (from the same directory as bot.py)
# Requires: pip install watchdog

import os
import subprocess
import sys
import time
from pathlib import Path

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("Install watchdog: pip install watchdog")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent


class RestartHandler(FileSystemEventHandler):
    def __init__(self, runner):
        self.runner = runner

    def on_modified(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith(".py"):
            self.runner.restart()


class DevRunner:
    def __init__(self):
        self.process = None

    def start_bot(self):
        self.process = subprocess.Popen(
            [sys.executable, str(ROOT / "bot.py")],
            cwd=str(ROOT),
            env=os.environ.copy(),
            stdout=sys.stdout,
            stderr=sys.stderr,
        )

    def stop_bot(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

    def restart(self):
        print("\n🔄 Change detected, restarting bot...")
        self.stop_bot()
        time.sleep(0.5)
        self.start_bot()

    def run(self):
        self.start_bot()
        observer = Observer()
        observer.schedule(RestartHandler(self), str(ROOT), recursive=True)
        observer.start()
        try:
            while True:
                if self.process and self.process.poll() is not None:
                    print("\n⚠️ Bot exited, restarting...")
                    self.start_bot()
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            observer.stop()
            observer.join()
            self.stop_bot()
            print("\n👋 Stopped.")


if __name__ == "__main__":
    DevRunner().run()
