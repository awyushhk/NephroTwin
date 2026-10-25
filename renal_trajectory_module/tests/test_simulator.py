import numpy as np
import pytest

from renal_trajectory_module import simulate_trajectory_v2


def test_standalone_simulation_outputs_and_lengths():
    t, egfr, uacr, threshold = simulate_trajectory_v2(55.0, 8.0, 300.0, 140.0, years=5, n=51)
    assert len(t) == len(egfr) == len(uacr) == 51
    assert np.isclose(t[0], 0) and np.isclose(t[-1], 5)
    assert np.all(np.isfinite(egfr)) and np.all(np.isfinite(uacr))
    assert egfr[0] == pytest.approx(55.0)
    assert isinstance(threshold, float)


def test_invalid_negative_horizon_uses_solver_error():
    # Upstream implementation delegates this invalid interval to solve_ivp.
    with pytest.raises(ValueError):
        simulate_trajectory_v2(55.0, 8.0, 300.0, 140.0, years=-1, n=51)
