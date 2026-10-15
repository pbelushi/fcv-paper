"""Executa o pipeline completo (equivalente a `make all`).

Uso: python run_all.py [--from 03]   # retoma a partir de uma etapa
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STEPS = sorted(p for p in (ROOT / "src").glob("[0-9][0-9]_*.py"))


def main() -> None:
    start = "00"
    if "--from" in sys.argv:
        start = sys.argv[sys.argv.index("--from") + 1].zfill(2)
    for step in STEPS:
        if step.name[:2] < start:
            continue
        print(f"\n===== {step.name} =====", flush=True)
        res = subprocess.run([sys.executable, str(step)], cwd=ROOT)
        if res.returncode != 0:
            sys.exit(f"Falha em {step.name} (código {res.returncode}); pipeline interrompido.")
    print("\nPipeline concluído.")


if __name__ == "__main__":
    main()
