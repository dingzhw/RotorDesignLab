import unittest
import numpy as np
from tools.audit_rotor_mass_sources import integrate_segments


class MassSourceTests(unittest.TestCase):
    def test_uniform_rod_and_partial_root(self):
        np.testing.assert_allclose(integrate_segments([0., 1., 3.], [2., 2.], 1.), [4., 4., 16/3])
        np.testing.assert_allclose(integrate_segments([0., 3.], [2.], 1.), [4., 4., 16/3])

    def test_raw_duplicate_or_invalid_density_is_not_silently_repaired(self):
        for edges, density in [([20., 22., 22., 23.], [1., 2., 3.]), ([0., 1.], [-1.])]:
            with self.assertRaises(ValueError):
                integrate_segments(edges, density, 0.)


if __name__ == '__main__':
    unittest.main()
