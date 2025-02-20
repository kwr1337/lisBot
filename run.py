import subprocess
from watchfiles import run_process, DefaultFilter

class CustomFilter(DefaultFilter):
    def __init__(self):
        super().__init__(
            ignore_patterns=["__pycache__", "*.pyc", ".git/*", "venv/*"]
        )

def run_bot():
    subprocess.run(["python", "bot.py"])

if __name__ == "__main__":
    # Следим за изменениями в папках
    run_process(
        ".", 
        target=run_bot,
        watch_filter=CustomFilter(),
    ) 