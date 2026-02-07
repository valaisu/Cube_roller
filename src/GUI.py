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
        props.setFullscreen(True)
        self.win.requestProperties(props)

        # Disable default mouse camera control
        self.disableMouse()

        # Setup camera
        self.camera_distance = 18
        self.camera_angle_h = 45
        self.camera_angle_p = 35
        self.update_camera()

        # Create scene
        self.setup_scene()
        self.setup_lighting()
        self.setup_controls()
        self.setup_ui()

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

        # Initialize cube counters (4 cubes each initially)
        self.update_cube_counters(4, 4)

    def setup_scene(self):
        """Create the game board and cubes"""
        self.cubes = []
        self.board_tiles = []

        # Board dimensions
        self.board_dim = [5, 7]
        top_spawn = [2, 3]
        bottom_spawn = [1, 2]

        # Create board tiles
        for x in range(self.board_dim[0]):
            for y in range(self.board_dim[1]):
                square = self.loader.loadModel("../assets/white_square.obj")
                square.setScale(1, 1, 1)
                square.setPos((x - self.board_dim[0]/2) * 1.1, (y - self.board_dim[1]/2) * 1.1, 0)
                square.setHpr(0, 90, 0)

                # Color coding
                if y == 0:
                    if x in top_spawn:
                        square.setColor(0.8, 0.2, 0.2, 1)  # Red spawn
                    else:
                        square.setColor(0.2, 0.2, 0.2, 1)  # Black out of bounds
                elif y == self.board_dim[1] - 1:
                    if x in bottom_spawn:
                        square.setColor(0.2, 0.2, 0.8, 1)  # Blue spawn
                    else:
                        square.setColor(0.2, 0.2, 0.2, 1)  # Black out of bounds
                else:
                    square.setColor(0.45, 0.45, 0.45, 1)  # Gray playable area

                square.reparentTo(self.render)
                self.board_tiles.append(square)

        # Create some demo cubes on the board
        cube_positions = [
            (2, 1, [('slide', 'top'), ('push', 'front'), ('rotate', 'right'),
                    ('fortify', 'back'), ('start', 'bottom'), ('strength', 'left')]),
            (2, 2, [('grapple', 'top'), ('detonate', 'front'), ('build', 'right'),
                    ('slash', 'back'), ('start', 'bottom'), ('rotate', 'left')]),
            (1, 5, [('push', 'top'), ('slide', 'front'), ('strength', 'right'),
                    ('grapple', 'back'), ('start', 'bottom'), ('fortify', 'left')]),
            (3, 4, [('detonate', 'top'), ('build', 'front'), ('slash', 'right'),
                    ('rotate', 'back'), ('start', 'bottom'), ('push', 'left')]),
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
            ('top', (0, 0, size), 0, -90, 180),       # facing +Z (up)
            ('bottom', (0, 0, -size), 0, 90, 180),    # facing -Z (down)
            ('front', (0, size, 0), 180, 0, 0),       # facing +Y (forward)
            ('back', (0, -size, 0), 0, 0, 180),       # facing -Y (backward)
            ('right', (size, 0, 0), 90, 0, -90),      # facing +X (right)
            ('left', (-size, 0, 0), -90, 0, 90),      # facing -X (left)
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

        # Keyboard controls for camera
        self.accept('escape', sys.exit)
        self.accept('r', self.reset_camera)
        self.accept('arrow_left', self.rotate_left)
        self.accept('arrow_right', self.rotate_right)
        self.accept('arrow_up', self.rotate_up)
        self.accept('arrow_down', self.rotate_down)
        self.accept('+', self.zoom_in)
        self.accept('-', self.zoom_out)
        self.accept('=', self.zoom_in)  # Allow = without shift

    def setup_ui(self):
        """Setup the side panel UI"""
        # Left sidebar - opaque and slightly wider than right
        self.left_panel = DirectFrame(
            frameColor=(0.18, 0.15, 0.15, 1.0),
            frameSize=(-1.95, -0.75, -1, 1),
            pos=(0, 0, 0)
        )

        # Player 1 section (RED - top half)
        player1_label = DirectLabel(
            text="Player 1",
            text_scale=0.07,
            text_fg=(1, 0.3, 0.3, 1),
            frameColor=(0, 0, 0, 0),
            pos=(-1.35, 0, 0.92),
            parent=self.left_panel
        )

        # Player 1 cube counter (8 symbols)
        self.player1_cube_symbols = []
        for i in range(8):
            x_offset = -0.28 + i * 0.08
            symbol = DirectFrame(
                frameColor=(1, 0.3, 0.3, 1),
                frameSize=(-0.025, 0.025, -0.025, 0.025),
                pos=(-1.35 + x_offset, 0, 0.83),
                parent=self.left_panel
            )
            self.player1_cube_symbols.append(symbol)

        # Player 1 cube displays (3 cubes side by side)
        self.player1_cube_containers = []
        for i in range(3):
            x_offset = -0.35 + i * 0.35
            container = self.aspect2d.attachNewNode(f"player1_cube_{i}")
            container.setPos(-1.35 + x_offset, 0, 0.5)
            self.player1_cube_containers.append(container)
            # Initially show empty cube
            self.display_flattened_cube(container, None, scale=0.8)

        # Player 2 section (BLUE - bottom half)
        player2_label = DirectLabel(
            text="Player 2",
            text_scale=0.07,
            text_fg=(0.3, 0.3, 1, 1),
            frameColor=(0, 0, 0, 0),
            pos=(-1.35, 0, -0.08),
            parent=self.left_panel
        )

        # Player 2 cube displays (3 cubes side by side)
        self.player2_cube_containers = []
        for i in range(3):
            x_offset = -0.35 + i * 0.35
            container = self.aspect2d.attachNewNode(f"player2_cube_{i}")
            container.setPos(-1.35 + x_offset, 0, -0.3)
            self.player2_cube_containers.append(container)
            # Initially show empty cube
            self.display_flattened_cube(container, None, scale=0.8)

        # Player 2 cube counter (8 symbols) - at very bottom
        self.player2_cube_symbols = []
        for i in range(8):
            x_offset = -0.28 + i * 0.08
            symbol = DirectFrame(
                frameColor=(0.3, 0.3, 1, 1),
                frameSize=(-0.025, 0.025, -0.025, 0.025),
                pos=(-1.35 + x_offset, 0, -0.95),
                parent=self.left_panel
            )
            self.player2_cube_symbols.append(symbol)

        # Right panel background - at the very right edge
        self.panel = DirectFrame(
            frameColor=(0.15, 0.15, 0.18, 1.0),
            frameSize=(0.85, 1.78, -1, 1),
            pos=(0, 0, 0)
        )

        # Title
        title = DirectLabel(
            text="Cube Roller",
            text_scale=0.08,
            text_fg=(1, 1, 1, 1),
            frameColor=(0, 0, 0, 0),
            pos=(1.315, 0, 0.9),
            parent=self.panel
        )

        # Info text
        self.info_label = DirectLabel(
            text="Click a cube to select",
            text_scale=0.045,
            text_fg=(0.9, 0.9, 0.9, 1),
            frameColor=(0, 0, 0, 0),
            pos=(1.315, 0, 0.8),
            text_wordwrap=20,
            parent=self.panel
        )

        # Unfolded cube display area
        cube_display_label = DirectLabel(
            text="Selected Cube:",
            text_scale=0.05,
            text_fg=(1, 1, 1, 1),
            frameColor=(0, 0, 0, 0),
            pos=(1.315, 0, 0.65),
            parent=self.panel
        )

        # Container for unfolded cube display
        self.unfolded_cube_container = self.aspect2d.attachNewNode("unfoldedCubeContainer")
        self.unfolded_cube_container.setPos(1.315, 0, 0.25)

        # Action buttons
        button_y = -0.2
        button_spacing = 0.12

        buttons = [
            ("Roll Cube", self.on_roll_cube),
            ("Build New", self.on_build_cube),
            ("Add Side", self.on_add_side),
            ("End Turn", self.on_end_turn),
        ]

        self.action_buttons = []
        for i, (text, command) in enumerate(buttons):
            btn = DirectButton(
                text=text,
                text_scale=0.045,
                text_fg=(1, 1, 1, 1),
                frameColor=(0.3, 0.4, 0.5, 1),
                frameSize=(-0.2, 0.2, -0.04, 0.04),
                pos=(1.315, 0, button_y - i * button_spacing),
                command=command,
                parent=self.panel,
                rolloverSound=None,
                clickSound=None,
            )
            self.action_buttons.append(btn)

        # Stats/visualization area
        stats_label = DirectLabel(
            text="Game Stats:",
            text_scale=0.05,
            text_fg=(1, 1, 1, 1),
            frameColor=(0, 0, 0, 0),
            pos=(1.315, 0, -0.7),
            parent=self.panel
        )

        self.stats_text = DirectLabel(
            text="Player 1 Turn\nCubes: 4\nMoves: 0",
            text_scale=0.04,
            text_fg=(0.8, 0.8, 0.8, 1),
            frameColor=(0.15, 0.15, 0.2, 1),
            frameSize=(-0.25, 0.25, -0.12, 0.12),
            pos=(1.315, 0, -0.85),
            text_wordwrap=15,
            parent=self.panel
        )

        # Instructions at the bottom
        instructions = DirectLabel(
            text="Arrow Keys: Rotate\n+/- : Zoom\nR: Reset camera",
            text_scale=0.035,
            text_fg=(0.6, 0.6, 0.6, 1),
            frameColor=(0, 0, 0, 0),
            pos=(1.315, 0, -0.95),
            text_wordwrap=18,
            parent=self.panel
        )

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
        """Select a cube and update UI"""
        # Deselect previous cube
        if self.selected_cube:
            # Reset scale
            self.selected_cube.setScale(1, 1, 1)

        # Select new cube
        self.selected_cube = cube_node
        cube_node.setScale(1.15, 1.15, 1.15)  # Highlight by scaling

        # Update info
        name = cube_node.getTag('name')
        cube_data = next((c for c in self.cubes if c['node'] == cube_node), None)

        if cube_data:
            icons_str = ", ".join([icon[0] for icon in cube_data['icons'][:3]]) + "..."
            self.info_label['text'] = f"Selected: {name}"
            # Display unfolded cube
            self.display_unfolded_cube(cube_data)
        else:
            self.info_label['text'] = name

    def deselect_cube(self):
        """Deselect current cube"""
        if self.selected_cube:
            self.selected_cube.setScale(1, 1, 1)
            self.selected_cube = None

        self.info_label['text'] = "Click a cube to select"
        # Clear unfolded cube display
        self.clear_unfolded_cube()

    def clear_unfolded_cube(self):
        """Clear the unfolded cube display"""
        self.unfolded_cube_container.removeNode()
        self.unfolded_cube_container = self.aspect2d.attachNewNode("unfoldedCubeContainer")
        self.unfolded_cube_container.setPos(1.315, 0, 0.25)

    def display_unfolded_cube(self, cube_data):
        """Display the selected cube in unfolded (cross) format"""
        # Clear previous display
        self.clear_unfolded_cube()

        # Face size for display
        face_size = 0.12

        # Load textures for this cube
        icon_dict = {}
        for icon_name, face in cube_data['icons']:
            icon_path = f"../assets/icons/{icon_name}.png"
            try:
                tex = self.loader.loadTexture(icon_path)
                icon_dict[face] = tex
            except:
                pass

        # Cross layout positions with top in the middle:
        #       [back]
        # [left][top][right]
        #      [front]
        #     [bottom]

        face_positions = {
            'top': (0, 0, 0),                      # center
            'back': (0, 0, face_size),             # above
            'bottom': (0, 0, -2 * face_size),      # below front
            'left': (-face_size, 0, 0),            # left of center
            'right': (face_size, 0, 0),            # right of center
            'front': (0, 0, -face_size),           # below center
        }

        for face_name, (x, y, z) in face_positions.items():
            cm = CardMaker(f"unfolded_{face_name}")
            cm.setFrame(-face_size/2, face_size/2, -face_size/2, face_size/2)
            face = self.unfolded_cube_container.attachNewNode(cm.generate())
            face.setPos(x, y, z)

            # Apply texture if available
            if face_name in icon_dict:
                face.setTexture(icon_dict[face_name])
                face.setColor(1, 1, 1, 1)
            else:
                # Default color
                face.setColor(0.4, 0.4, 0.5, 1)

    def update_cube_counters(self, player1_count, player2_count):
        """Update the cube counter displays for both players (grayed out for used)"""
        # Update player 1 symbols (show all 8, gray out used ones)
        for i, symbol in enumerate(self.player1_cube_symbols):
            if i < player1_count:
                # Remaining cubes - bright red
                symbol['frameColor'] = (1, 0.3, 0.3, 1)
            else:
                # Used cubes - grayed out
                symbol['frameColor'] = (0.3, 0.2, 0.2, 0.5)

        # Update player 2 symbols (show all 8, gray out used ones)
        for i, symbol in enumerate(self.player2_cube_symbols):
            if i < player2_count:
                # Remaining cubes - bright blue
                symbol['frameColor'] = (0.3, 0.3, 1, 1)
            else:
                # Used cubes - grayed out
                symbol['frameColor'] = (0.2, 0.2, 0.3, 0.5)

    def display_flattened_cube(self, container, cube_data, scale=1.0):
        """Display a flattened cube in the given container (can be None for empty cube)"""
        # Clear previous display
        for child in container.getChildren():
            child.removeNode()

        # Face size for display (smaller for left panel, scaled by parameter)
        face_size = 0.08 * scale

        # Cross layout positions with top in the middle:
        #       [back]
        # [left][top][right]
        #      [front]
        #     [bottom]

        face_positions = {
            'top': (0, 0, 0),                      # center
            'back': (0, 0, face_size),             # above
            'bottom': (0, 0, -2 * face_size),      # below front
            'left': (-face_size, 0, 0),            # left of center
            'right': (face_size, 0, 0),            # right of center
            'front': (0, 0, -face_size),           # below center
        }

        # Load textures if cube_data is provided
        icon_dict = {}
        if cube_data:
            for icon_name, face in cube_data['icons']:
                icon_path = f"../assets/icons/{icon_name}.png"
                try:
                    tex = self.loader.loadTexture(icon_path)
                    icon_dict[face] = tex
                except:
                    pass

        for face_name, (x, y, z) in face_positions.items():
            cm = CardMaker(f"flat_{face_name}")
            cm.setFrame(-face_size/2, face_size/2, -face_size/2, face_size/2)
            face = container.attachNewNode(cm.generate())
            face.setPos(x, y, z)

            # Apply texture if available, otherwise show empty
            if face_name in icon_dict:
                face.setTexture(icon_dict[face_name])
                face.setColor(1, 1, 1, 1)
            else:
                # Empty/default color
                face.setColor(0.3, 0.3, 0.35, 1)

    def on_roll_cube(self):
        """Handle roll cube button"""
        if self.selected_cube:
            self.info_label['text'] = "Rolling cube... (not implemented)"
        else:
            self.info_label['text'] = "Select a cube first!"

    def on_build_cube(self):
        """Handle build new cube button"""
        self.info_label['text'] = "Building new cube... (not implemented)"

    def on_add_side(self):
        """Handle add side button"""
        if self.selected_cube:
            self.info_label['text'] = "Adding side... (not implemented)"
        else:
            self.info_label['text'] = "Select a cube first!"

    def on_end_turn(self):
        """Handle end turn button"""
        self.info_label['text'] = "Ending turn... (not implemented)"

    def rotate_left(self):
        """Rotate camera left"""
        self.camera_angle_h -= 15
        self.update_camera()

    def rotate_right(self):
        """Rotate camera right"""
        self.camera_angle_h += 15
        self.update_camera()

    def rotate_up(self):
        """Rotate camera up"""
        self.camera_angle_p = min(89, self.camera_angle_p + 10)
        self.update_camera()

    def rotate_down(self):
        """Rotate camera down"""
        self.camera_angle_p = max(-89, self.camera_angle_p - 10)
        self.update_camera()

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

        # Rotate around board center (0, 0, 0)
        x = self.camera_distance * math.cos(rad_p) * math.sin(rad_h)
        y = self.camera_distance * math.cos(rad_p) * math.cos(rad_h)
        z = self.camera_distance * math.sin(rad_p)

        self.camera.setPos(x, y, z)
        self.camera.lookAt(0, 0, 0)

        # Center the board between left and right sidebars
        lens = self.cam.node().getLens()
        lens.setFilmOffset(0, 0)


if __name__ == '__main__':
    game = CubeGameGUI()
    game.run()
