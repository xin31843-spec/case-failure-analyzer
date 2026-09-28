# General Scientific Computing & Numerical Solvers (`generic-scientific`: SciPy, NumPy, JAX, PyTorch, Sundials, FEniCS, OpenFOAM)

This reference defines the diagnostic error families, candidate causes, and required discriminating evidence for general scientific computing, ODE/PDE numerical solvers, linear algebra routines, nonlinear optimization, and physical unit transformations.
Remember: **Matching an error family does NOT automatically blame the agent.**

## Error Families

| Error Family | Signature Patterns | Candidate Causes | Required Discriminating Evidence |
|---|---|---|---|
| `linalg_singular_ill_conditioned` | `LinAlgError: Singular matrix`, `LinAlgError: Matrix is not positive definite`, `ArpackNoConvergence`, `ill-conditioned matrix` | `collinear_or_rank_deficient_design_matrix_or_jacobian`, `missing_tikhonov_regularization_or_gauge_fixing_boundary_condition`, `zero_diagonal_pivot_from_unconstrained_rigid_body_modes` | Check matrix condition number `np.linalg.cond(A)`, boundary condition rank, and regularization parameter |
| `ode_pde_solver_divergence` | `Required step size is less than spacing between numbers`, `IntegrationWarning: Excess work done`, `Courant number .* exceeds`, `FloatingPointError: overflow encountered` | `explicit_rk45_euler_solver_used_on_stiff_ode_system_instead_of_bdf_radau`, `cfl_condition_violated_dt_too_large_for_spatial_mesh_dx`, `unphysical_initial_or_boundary_value_discontinuity` | Compare stiffness ratio, solver method (`RK45` vs `Radau`/`BDF`), and $\Delta t / \Delta x^2$ CFL stability criterion |
| `nonlinear_optimization_nonconvergence` | `Positive directional derivative for linesearch`, `Maximum number of function evaluations has been exceeded`, `Desired error not necessarily achieved due to precision loss` | `inconsistent_analytical_gradient_vs_finite_difference_objective`, `unscaled_decision_variables_spanning_many_orders_of_magnitude`, `noisy_stochastic_objective_passed_to_l_bfgs_b_slsqp` | Check `scipy.optimize.check_grad`, parameter scaling, and `OptimizeResult.message` / gradient norm |
| `unit_dimensionality_scaling_error` | `DimensionError:.*incompatible units`, `UnitConversionError`, `off by factor of (27.21\|627.5\|4.184\|0.529\|13.605)` | `hartree_to_ev_or_kcal_mol_conversion_omitted`, `bohr_to_angstrom_or_nm_length_scale_mismatch`, `kbar_to_gpa_or_bar_to_atm_pressure_conversion_factor_error` | Compare ratio between agent value and reference value against fundamental constants ($27.2114\text{ eV/Ha}$, $0.529177\text{ \AA/Bohr}$, $4.184\text{ kJ/kcal}$, $10\text{ kbar/GPa}$) |
