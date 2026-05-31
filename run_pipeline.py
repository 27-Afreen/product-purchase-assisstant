import subprocess
import sys

scripts = [
    "src/scraper/create_seed_dataset.py",
    "src/preprocessing/clean_reviews.py",
    "src/analysis/basic_sentiment.py"
]

print("Pipeline started...")

for script in scripts:
    print(f"\nRunning: {script}")
    result = subprocess.run([sys.executable, script], capture_output=True, text=True)

    print("Return code:", result.returncode)

    if result.stdout:
        print("STDOUT:")
        print(result.stdout)

    if result.stderr:
        print("STDERR:")
        print(result.stderr)

print("\nPipeline completed.")