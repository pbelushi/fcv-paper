"""Executa o pipeline da rodada 2 de ponta a ponta.

Pré-requisito: dados da rodada 1 já processados (python run_all.py), pois a rodada 2 reutiliza
data/interim/poverty.parquet, conflict_cy.parquet, controls.parquet e as tabelas da rodada 1.
ACLED não entra: aguarda credenciais (.env com ACLED_EMAIL e ACLED_KEY).

Uso: python run_r2.py [--from d3]
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STEPS = ["d1_download", "d2_fcs", "d3_treatment", "d4_panel", "01_anatomy", "02_survey_effect", "03_gdp_effect",
         "04_gdp_passthrough", "05_poverty", "06_robustness", "07_report"]


def main() -> None:
    start = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else STEPS[0]
    for step in STEPS[STEPS.index(start):]:
        print(f"\n===== r2/{step}.py =====", flush=True)
        res = subprocess.run([sys.executable, str(ROOT / "src" / "r2" / f"{step}.py")], cwd=ROOT)
        if res.returncode != 0:
            sys.exit(f"Falha em {step} (código {res.returncode}); pipeline interrompido.")
    print("\nTestes da rodada 2:")
    subprocess.run([sys.executable, str(ROOT / "tests" / "r2" / "test_r2.py")], cwd=ROOT, check=True)
    print("\nPipeline da rodada 2 concluído.")


if __name__ == "__main__":
    main()
