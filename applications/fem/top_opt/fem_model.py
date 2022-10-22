import numpy as onp
import jax
import jax.numpy as np

from jax_am.fem.jax_fem import Laplace


class Elasticity(Laplace):
    def __init__(self, name, mesh, linear_flag, dirichlet_bc_info=None, neumann_bc_info=None, source_info=None):
        self.name = name
        self.vec = 3
        super().__init__(mesh, dirichlet_bc_info, neumann_bc_info, source_info)
        self.neumann_boundary_inds = self.Neuman_boundary_conditions_inds(neumann_bc_info[0])[0]
        self.cell_centroids = onp.mean(onp.take(self.points, self.cells, axis=0), axis=1)
        self.flex_inds = np.arange(len(self.cells))
        self.params = np.ones_like(self.flex_inds)
        if linear_flag:
            self.get_tensor_map = self.get_tensor_map_linearelasticity
        else:
            self.get_tensor_map = self.get_tensor_map_hyperelasticity

    def get_tensor_map_linearelasticity(self):
        def stress(u_grad, theta):
            Emax = 70.e3
            Emin = 70.
            nu = 0.3
            penal = 3.
            E = Emin + (Emax - Emin)*(theta+0.01)**penal
            mu = E/(2.*(1. + nu))
            lmbda = E*nu/((1+nu)*(1-2*nu))
            epsilon = 0.5*(u_grad + u_grad.T)
            sigma = lmbda*np.trace(epsilon)*np.eye(self.dim) + 2*mu*epsilon
            return sigma
        return stress

    def get_tensor_map_hyperelasticity(self):
        def psi(F, theta):
            Emax = 1e3
            Emin = 1.
            nu = 0.3
            penal = 3.
            E = Emin + (Emax - Emin)*(theta+0.01)**penal
            mu = E/(2.*(1. + nu))
            kappa = E/(3.*(1. - 2.*nu))
            J = np.linalg.det(F)
            Jinv = J**(-2./3.)
            I1 = np.trace(F.T @ F)
            energy = (mu/2.)*(Jinv*I1 - 3.) + (kappa/2.) * (J - 1.)**2.
            return energy
        P_fn = jax.grad(psi)

        def first_PK_stress(u_grad, theta):
            I = np.eye(self.dim)
            F = u_grad + I
            P = P_fn(F, theta)
            return P
        return first_PK_stress

    def set_params(self):
        full_params = np.ones(self.num_cells)
        full_params = full_params.at[self.flex_inds].set(self.params)
        thetas = np.repeat(full_params[:, None], self.num_quads, axis=1)
        self.full_params = full_params
        return thetas

    def compute_residual(self, sol):
        thetas = self.set_params()
        return self.compute_residual_vars(sol, laplace=[thetas])

    def newton_update(self, sol):
        thetas = self.set_params()
        return self.newton_vars(sol, laplace=[thetas])

    def compute_compliance(self, neumann_fn, sol):
        boundary_inds = self.neumann_boundary_inds
        _, nanson_scale = self.get_face_shape_grads(boundary_inds)
        # (num_selected_faces, 1, num_nodes, vec) * # (num_selected_faces, num_face_quads, num_nodes, 1)    
        u_face = sol[self.cells][boundary_inds[:, 0]][:, None, :, :] * self.face_shape_vals[boundary_inds[:, 1]][:, :, :, None]
        u_face = np.sum(u_face, axis=2) # (num_selected_faces, num_face_quads, vec)
        # (num_cells, num_faces, num_face_quads, dim) -> (num_selected_faces, num_face_quads, dim)
        subset_quad_points = self.get_physical_surface_quad_points(boundary_inds)
        traction = jax.vmap(jax.vmap(neumann_fn))(subset_quad_points) # (num_selected_faces, num_face_quads, vec)
        val = np.sum(traction * u_face * nanson_scale[:, :, None])
        return val
