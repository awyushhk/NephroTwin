"""Synthetic demonstration inputs; these are not patient data."""
from pathlib import Path
import sys

# Make direct execution from the repository root or this file's folder work.
sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))
from renal_trajectory_module import simulate_trajectory_v2


def main():
    t, egfr, uacr, t_threshold = simulate_trajectory_v2(
        egfr0=47.7, a1c=8.1, uacr0=145.0, sbp=142.0,
        u=0.0, years=15, n=400,
    )
    print(f"eGFR < 15 crossing (years): {t_threshold}")
    print("time_years,eGfr_ml_min_1.73m2,uacr_mg_g")
    for time, gfr, albuminuria in zip(t, egfr, uacr):
        print(f"{time:.6g},{gfr:.6g},{albuminuria:.6g}")


if __name__ == "__main__":
    main()
