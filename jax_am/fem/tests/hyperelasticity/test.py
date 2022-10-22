import numpy as onp
import numpy.testing as onptest
import jax
import jax.numpy as np
import meshio
import unittest
from jax_am.fem.jax_fem import Mesh, HyperElasticity
from jax_am.fem.solver import solver
from jax_am.fem.utils import modify_vtu_file, save_sol


class Test(unittest.TestCase):
    """Test hyper-elasticity with cylinder mesh
    """
    def test_solve_problem(self):
        """Compare FEniCSx solution with JAX-FEM
        """
        problem_name = "hyperelasticity"
        fenicsx_vtu_path_raw = f"jax_am/fem/tests/{problem_name}/fenicsx/sol_p0_000000.vtu"
        fenicsx_vtu_path = f"jax_am/fem/tests/{problem_name}/fenicsx/sol.vtu"
        modify_vtu_file(fenicsx_vtu_path_raw, fenicsx_vtu_path)
        fenicsx_vtu = meshio.read(fenicsx_vtu_path)
        cells = fenicsx_vtu.cells_dict['VTK_LAGRANGE_HEXAHEDRON'] # 'hexahedron'
        points = fenicsx_vtu.points
        mesh = Mesh(points, cells)
        H = 10.

        def top(point):
            return np.isclose(point[2], H, atol=1e-5)

        def bottom(point):
            return np.isclose(point[2], 0., atol=1e-5)

        def dirichlet_val_bottom(point):
            return 0.

        def dirichlet_val_top(point):
            return 1.

        location_fns = [bottom, bottom, bottom, top, top, top]
        value_fns = [dirichlet_val_bottom, dirichlet_val_bottom, dirichlet_val_bottom, 
                     dirichlet_val_bottom, dirichlet_val_bottom, dirichlet_val_top]
        vecs = [0, 1, 2, 0, 1, 2]
        dirichlet_bc_info = [location_fns, vecs, value_fns]

        problem = HyperElasticity(f"{problem_name}", mesh, dirichlet_bc_info=dirichlet_bc_info)
        sol = solver(problem)

        jax_vtu_path = f"jax_am/fem/tests/{problem_name}/jax_fem/sol.vtu"
        save_sol(problem, sol, jax_vtu_path)
        jax_fem_vtu = meshio.read(jax_vtu_path)

        jax_fem_sol = jax_fem_vtu.point_data['sol']
        fenicsx_sol = fenicsx_vtu.point_data['sol'].reshape(jax_fem_sol.shape)

        print(f"Solution absolute value differs by {np.max(np.absolute(jax_fem_sol - fenicsx_sol))} between FEniCSx and JAX-FEM")
        onptest.assert_array_almost_equal(fenicsx_sol, jax_fem_sol, decimal=5)

        fenicsx_traction = np.load(f"jax_am/fem/tests/{problem_name}/fenicsx/traction.npy")
        jax_fem_traction = problem.compute_traction(top, sol)[2]

        print(f"FEniCSx computes traction (z-axis) to be {fenicsx_traction}")
        print(f"JAX-FEM computes traction (z-axis) to be {jax_fem_traction}")

        onptest.assert_almost_equal(fenicsx_traction, jax_fem_traction, decimal=5)


if __name__ == '__main__':
    unittest.main()
