Feature: Spatial Geometry Subsystem
Domain: Analytics (Math Engine)

Business Context:
The analytics team needs spatial volume calculations. Expand the existing mathematical subsystem by introducing a modular, multi-file geometry package.

Acceptance Criteria:
1. Architecture: Separate the domain into core interfaces, 2D shapes, and 3D volume calculators.
2. Interfaces: Define an abstract base class `Shape` with an abstract method for calculating area.
3. 2D Implementation: Implement `Circle` (initialized with radius) and `Rectangle` (initialized with width and height) extending the base `Shape`.
4. 3D Implementation: Implement volume calculation functions for standard 3D extrusions (Cylinder, Cuboid) that consume the 2D shape logic.
5. Safety constraint: All dimensions must be strictly numeric (no booleans) and strictly greater than zero. Violations must raise appropriate standard exceptions.