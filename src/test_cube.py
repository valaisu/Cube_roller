from direct.showbase.ShowBase import ShowBase
from panda3d.core import *
from direct.gui.DirectGui import *
from direct.task import Task
import sys
import random

class CubeGameGUI(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)

        # Window configuration
        props = WindowProperties()
        props.setTitle("Cube Roller Game")
        self.win.requestProperties(props)

        # Disable default mouse camera control
        self.disableMouse()

        # Setup camera
        self.camera_distance = 18
        self.camera_angle_h = 45
        self.camera_angle_p = 35
        self.update_camera()

        # Track mouse state
        self.last_mouse_x = 0
        self.last_mouse_y = 0
        self.mouse_dragging = False

        # Create scene
        self.setup_scene()
        self.setup_lighting()
        self.setup_controls()

        # Setup object picking
        self.picker = CollisionTraverser()
        self.pq = CollisionHandlerQueue()
        self.pickerNode = CollisionNode('mouseRay')
        self.pickerNP = self.camera.attachNewNode(self.pickerNode)
        self.pickerNode.setFromCollideMask(GeomNode.getDefaultCollideMask())
        self.pickerRay = CollisionRay()
        self.pickerNode.addSolid(self.pickerRay)
        self.picker.addCollider(self.pickerNP, self.pq)

        # Selected cube
        self.selected_cube = None

    def setup_scene(self):
        """Create the game board and cubes"""
        self.cubes = []
        self.board_tiles = []

        # Board dimensions
        self.board_dim = [5, 7]

        # Create some demo cubes on the board
        cube_positions = [
            (2, 1, [('slide', 'top'), ('push', 'front'), ('rotate', 'right'),
                    ('fortify', 'back'), ('start', 'bottom'), ('strength', 'left')]),
        ]

        for x, y, icons in cube_positions:
            cube = self.create_cube(x, y, icons)
            self.cubes.append({'node': cube, 'board_pos': (x, y), 'icons': icons})

    def create_cube(self, board_x, board_y, icon_faces):
        """Create a cube with icons on its faces"""
        # Create cube geometry
        cube = self.render.attachNewNode("cube")

        # Load available icons
        icon_dict = {}
        for icon_name, face in icon_faces:
            icon_path = f"../assets/icons/{icon_name}.png"
            try:
                tex = self.loader.loadTexture(icon_path)
                tex.setMinfilter(Texture.FTLinearMipmapLinear)
                tex.setMagfilter(Texture.FTLinear)
                icon_dict[face] = tex
            except:
                print(f"Warning: Could not load texture {icon_path}")

        # Create cube faces
        # size is half the cube's side length
        size = 0.4

        # CardMaker creates cards in XY plane facing +Z
        # We position each face 'size' distance from center along its normal
        faces_config = [
            # (name, position, heading, pitch, roll)
            ('top', (0, 0, size), 0, -90, 180),           # facing +Z (up) # slide 1
            ('bottom', (0, 0, -size), 0, 90, 180),     # facing -Z (down) # start
            ('front', (0, size, 0), 180, 0, 0),       # facing +Y (forward) #  push?
            ('back', (0, -size, 0), 0, 0, 180),        # facing -Y (backward) # fortify 1
            ('right', (size, 0, 0), 90, 0, -90),       # facing +X (right) rotate 1
            ('left', (-size, 0, 0), -90, 0, 90),        # facing -X (left) # strength 1
        ]

        for face_name, pos, h, p, r in faces_config:
            cm = CardMaker(f"face_{face_name}")
            cm.setFrame(-size, size, -size, size)
            face = cube.attachNewNode(cm.generate())
            face.setPos(*pos)
            face.setHpr(h, p, r)

            # Apply texture if available
            if face_name in icon_dict:
                face.setTexture(icon_dict[face_name])
                face.setColor(1, 1, 1, 1)
            else:
                # Default color if no texture
                face.setColor(0.6, 0.6, 0.7, 1)

        # Position cube on board
        world_x = (board_x - self.board_dim[0]/2) * 1.1
        world_y = (board_y - self.board_dim[1]/2) * 1.1
        cube.setPos(world_x, world_y, size + 0.05)

        # Add collision detection
        self.add_collision(cube, f'cube_{board_x}_{board_y}')
        cube.setTag('name', f'Cube ({board_x},{board_y})')
        cube.setTag('type', 'cube')

        return cube

    def add_collision(self, node, name):
        """Add collision detection to an object"""
        bounds = node.getBounds()
        center = bounds.getCenter()
        radius = bounds.getRadius()

        collision_node = CollisionNode(name)
        collision_node.addSolid(CollisionSphere(center, radius))
        collision_np = node.attachNewNode(collision_node)

    def setup_lighting(self):
        """Setup scene lighting"""
        # Ambient light
        alight = AmbientLight('alight')
        alight.setColor((0.5, 0.5, 0.5, 1))
        alnp = self.render.attachNewNode(alight)
        self.render.setLight(alnp)

        # Directional light
        dlight = DirectionalLight('dlight')
        dlight.setColor((0.7, 0.7, 0.7, 1))
        dlnp = self.render.attachNewNode(dlight)
        dlnp.setHpr(45, -60, 0)
        self.render.setLight(dlnp)

        # Additional light from the other side
        dlight2 = DirectionalLight('dlight2')
        dlight2.setColor((0.3, 0.3, 0.3, 1))
        dlnp2 = self.render.attachNewNode(dlight2)
        dlnp2.setHpr(-135, -45, 0)
        self.render.setLight(dlnp2)

    def setup_controls(self):
        """Setup keyboard and mouse controls"""
        # Mouse controls
        self.accept('mouse1', self.on_mouse_click)
        self.accept('mouse3', self.start_drag)
        self.accept('mouse3-up', self.stop_drag)
        self.accept('wheel_up', self.zoom_in)
        self.accept('wheel_down', self.zoom_out)

        # Keyboard
        self.accept('escape', sys.exit)
        self.accept('r', self.reset_camera)

        # Mouse movement task
        self.taskMgr.add(self.mouse_task, "mouseTask")




    def on_mouse_click(self):
        """Handle left mouse click for cube selection"""
        if self.mouseWatcherNode.hasMouse():
            mpos = self.mouseWatcherNode.getMouse()

            # Cast ray from camera through mouse position
            self.pickerRay.setFromLens(self.camNode, mpos.getX(), mpos.getY())

            self.picker.traverse(self.render)
            if self.pq.getNumEntries() > 0:
                self.pq.sortEntries()
                picked_obj = self.pq.getEntry(0).getIntoNodePath()

                # Find the parent node
                picked_node = picked_obj.findNetTag('name')
                if not picked_node.isEmpty():
                    obj_type = picked_node.getTag('type')
                    if obj_type == 'cube':
                        self.select_cube(picked_node)
            else:
                self.deselect_cube()

    def select_cube(self, cube_node):
        """Select a cube"""
        if self.selected_cube:
            self.selected_cube.setScale(1, 1, 1)

        self.selected_cube = cube_node
        cube_node.setScale(1.15, 1.15, 1.15)

    def deselect_cube(self):
        """Deselect current cube"""
        if self.selected_cube:
            self.selected_cube.setScale(1, 1, 1)
            self.selected_cube = None


    def start_drag(self):
        """Start camera rotation drag"""
        if self.mouseWatcherNode.hasMouse():
            self.mouse_dragging = True
            mpos = self.mouseWatcherNode.getMouse()
            self.last_mouse_x = mpos.getX()
            self.last_mouse_y = mpos.getY()

    def stop_drag(self):
        """Stop camera rotation drag"""
        self.mouse_dragging = False

    def mouse_task(self, task):
        """Handle mouse dragging for camera rotation"""
        if self.mouse_dragging and self.mouseWatcherNode.hasMouse():
            mpos = self.mouseWatcherNode.getMouse()
            dx = mpos.getX() - self.last_mouse_x
            dy = mpos.getY() - self.last_mouse_y

            self.camera_angle_h -= dx * 100
            self.camera_angle_p += dy * 50
            self.camera_angle_p = max(-89, min(89, self.camera_angle_p))

            self.last_mouse_x = mpos.getX()
            self.last_mouse_y = mpos.getY()

            self.update_camera()

        return Task.cont

    def zoom_in(self):
        """Zoom camera in"""
        self.camera_distance = max(8, self.camera_distance - 1)
        self.update_camera()

    def zoom_out(self):
        """Zoom camera out"""
        self.camera_distance = min(35, self.camera_distance + 1)
        self.update_camera()

    def reset_camera(self):
        """Reset camera to default position"""
        self.camera_distance = 18
        self.camera_angle_h = 45
        self.camera_angle_p = 35
        self.update_camera()

    def update_camera(self):
        """Update camera position based on spherical coordinates"""
        import math
        rad_h = math.radians(self.camera_angle_h)
        rad_p = math.radians(self.camera_angle_p)

        x = self.camera_distance * math.cos(rad_p) * math.sin(rad_h)
        y = self.camera_distance * math.cos(rad_p) * math.cos(rad_h)
        z = self.camera_distance * math.sin(rad_p)

        self.camera.setPos(x, y, z)
        self.camera.lookAt(0, 0, 0)


if __name__ == '__main__':
    game = CubeGameGUI()
    game.run()
