import numpy as np
from nanocut.body import Body
from .output import error
import nanocut.common as nc

class Periodic1DPrism(Body):
    """Class for periodic bodies bounded by a group of planes."""
    
    # (type, shape, optional, has_coordsys_version)
    arguments = {
                 "planes_normal": ( "floatarray", (-1,4), True, True ),
                 "planes_miller": ( "floatarray", (-1,4), True, False ),                 
                 }


    def __init__(self, geometry, period, configdict=None, **kwargs):
        """Extends the constructor of the class Body.
        
        Additional keywords:
            planes_normal: Plane defintions with normal vectors and distances.
            planes_miller: Plane definitions with miller indices and distances.
        """
        Body.__init__(self, geometry, configdict=configdict, **kwargs)
        kwargs.update(self.parse_arguments(Periodic1DPrism.arguments,
                                           configdict))
        
        # Convert miller index specifications to normal vectors
        miller_defs = kwargs.get("planes_miller", None)
        if miller_defs is not None:
            if np.any(np.all(abs(miller_defs[:,0:3]) < 1e-12, axis=1)):
                error("Emtpy miller index tuple")
            miller_defs[:,0:3] = nc.miller_to_normal(geometry._latvecs,
                                                     miller_defs[:,0:3])
        else:
            miller_defs = np.zeros((0, 4), dtype=float)
            
        # Convert plane normal vector specifications into cartesian coords.
        normal_defs = kwargs.get("planes_normal", None)
        if normal_defs is not None:
            normal_defs[:,0:3] = geometry.coord_transform(
                normal_defs[:,0:3],
                kwargs.get("planes_normal_coordsys", "lattice"))
            if np.any(np.all(abs(normal_defs[:,0:3]) < 1e-12, axis=1)):
                error("Emtpy normal vector definition")
        else:
            normal_defs = np.zeros((0, 4), dtype=float)

        # Append two defintions
        planes_normal = np.vstack(( miller_defs, normal_defs ))
        
        # Check for planes normals not orthogonal to axis (plane cuts axis)
        axis = period.get_axis("cartesian")
        print(planes_normal.shape, axis.transpose().shape)
        print(axis)
        print(planes_normal[:,:3])
        projections = abs(np.dot(planes_normal[:,:3], axis.transpose()))
        print(projections) 
        if np.any(projections > 1e-8):            
            error("Some plane(s) are not parallel to axis")
        
        # Norm normal vectors
        norms = np.sqrt(np.sum(planes_normal[:,0:3]**2, axis=1))
        planes_normal[:,0:3] /= norms[:,np.newaxis] 

        # Remove identical planes (identical = parallel, but not antiparallel,
        # with similar distance from origin)
        unique = np.ones(( len(planes_normal), ), dtype=bool)
        for i1 in range(len(planes_normal)):
            if not unique[i1]:
                continue
            for i2 in range(i1 + 1, len(planes_normal)):
                if not unique[i2]:
                    continue
                ddiff = planes_normal[i1, 3] - planes_normal[i2, 3]
                cross = np.cross(planes_normal[i1, 0:3], planes_normal[i2, 0:3])
                vsum = planes_normal[i1, 0:3] + planes_normal[i2, 0:3]
                unique[i2] = (abs(ddiff) > 1e-12 or np.any(abs(cross)) > 1e-12
                              or np.all(abs(vsum) < 1e-12))
        self.planes_normal = planes_normal[unique]
        
        # Determine basal planes. Shift them with a tolerance to make
        # polyhedron bigger. 
        axisnorm = np.linalg.norm(axis[0])
        axis0 = axis[0] / axisnorm
        basal_planes = np.array(
            [[ axis0[0], axis0[1], axis0[2], -1e-3 ],
             [ axis0[0], axis0[1], axis0[2], axisnorm + 1e-3 ]])
        self.planes_normal = np.vstack(basal_planes, self._planes_normal)
         
        # Solve a linear equation for each triplet of planes returning their
        # vertex, ignore parallel planes
        self.corners = []
        for i1 in range(0, len(self.planes_normal)):
            for i2 in range(i1 + 1, len(self.planes_normal)):
                for i3 in range(2):
                    try:
                        corner = np.linalg.solve(
                            np.vstack((
                                self.planes_normal[i1, 0:3],
                                self.planes_normal[i2, 0:3],
                                self.planes_normal[i3, 0:3]
                                )),
                            np.vstack((
                                self.planes_normal[i1, 3],
                                self.planes_normal[i2, 3],
                                self.planes_normal[i3, 3]
                                )
                            ))
                        self.corners.append(corner.flatten())
                    except np.linalg.linalg.LinAlgError:
                        pass
        self.corners = np.array(self.corners)

        if np.all(len(self.corners) < 6 or abs(self.corners) < 1e-12):
            exit('Error:\nNo or insufficient corners found.\nExiting...\n')
        self.corners += self.shift_vector


    def containing_cuboid(self,period):
        """Returns the edges of the containing cuboid (see Body class)."""
        return np.vstack(( self._corners.min(axis=0),
                           self._corners.max(axis=0) ))

    def atoms_inside(self, atoms, periodicity=None):
        """Decides which atoms are inside the body (see Body class)."""
        
        shift = self.shift_vector [0]   # shift_vector is of shape (1, 3)
        # An atom is inside, if projections along all plane normals have the
        # same sign as an arbitrary point (center of mass) in the polyhedron. 
        point_inside = (np.sum(self.corners, axis=0) / float(len(self.corners))
                        - shift)
        atoms_relative = atoms[:,:3] - shift        
        normvecs = np.transpose(self.planes_normal[:,0:3])
        normdists = self.planes_normal[:,3]
        sign_point = (normdists - np.dot(point_inside, normvecs) <= 0.0)
        sign_atoms = (normdists - np.dot(atoms_relative, normvecs) <= 0.0)
        compared = (sign_atoms == sign_point)
        atoms_inside_body = np.all(compared, axis=1)
        return atoms_inside_body