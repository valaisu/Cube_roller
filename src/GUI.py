from direct.showbase.ShowBase import ShowBase
from panda3d.core import *
from direct.gui.DirectGui import *
from direct.gui import DirectGuiGlobals as DGG
from direct.task import Task
import sys
import random
import os
import math

# Screen dimensions
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
ASPECT_RATIO = SCREEN_WIDTH / SCREEN_HEIGHT

# In Panda3D aspect2d, vertical range is -1 to 1, horizontal is -ASPECT_RATIO to ASPECT_RATIO
SCREEN_LEFT = -ASPECT_RATIO
SCREEN_RIGHT = ASPECT_RATIO

# Panel widths as fractions of total screen width
LEFT_PANEL_WIDTH = 0.30   # 30% of screen
RIGHT_PANEL_WIDTH = 0.22  # 22% of screen

# Calculate panel boundaries in aspect2d coordinates
LEFT_PANEL_LEFT = SCREEN_LEFT
LEFT_PANEL_RIGHT = SCREEN_LEFT + (LEFT_PANEL_WIDTH * 2 * ASPECT_RATIO)
LEFT_PANEL_CENTER = (LEFT_PANEL_LEFT + LEFT_PANEL_RIGHT) / 2

RIGHT_PANEL_RIGHT = SCREEN_RIGHT
RIGHT_PANEL_LEFT = SCREEN_RIGHT - (RIGHT_PANEL_WIDTH * 2 * ASPECT_RATIO)
RIGHT_PANEL_CENTER = (RIGHT_PANEL_LEFT + RIGHT_PANEL_RIGHT) / 2

# Game area (between panels)
GAME_AREA_LEFT = LEFT_PANEL_RIGHT
GAME_AREA_RIGHT = RIGHT_PANEL_LEFT
GAME_AREA_CENTER = (GAME_AREA_LEFT + GAME_AREA_RIGHT) / 2

# Number of under-construction cube slots open per player at game start (easy to change)
PLAYER_START_OPEN_CUBES = 1


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
        self.setup_roll_menu()
        self.setup_add_side_menu()

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

        # Turn tracking (1 = Player 1, 2 = Player 2)
        self.current_player = 1

        # Initialize cube counters (4 cubes each initially)
        self.update_cube_counters(4, 4)

        # Deferred deselect: set by on_mouse_click, cancelled by any GUI button handler.
        # A task running at sort=200 (after the event manager) checks both flags.
        self._deselect_pending = False
        self._gui_button_clicked = False
        self.taskMgr.add(self._process_pending_deselect, 'process_pending_deselect', sort=200)

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
        # Left sidebar
        self.left_panel = DirectFrame(
            frameColor=(0.18, 0.15, 0.15, 1.0),
            frameSize=(LEFT_PANEL_LEFT, LEFT_PANEL_RIGHT, -1, 1),
            pos=(0, 0, 0)
        )

        # Player 1 section (RED - top half)
        player1_label = DirectLabel(
            text="Player 1",
            text_scale=0.07,
            text_fg=(1, 0.3, 0.3, 1),
            text_align=TextNode.ACenter,
            frameColor=(0, 0, 0, 0),
            pos=(LEFT_PANEL_CENTER, 0, 0.92),
            parent=self.left_panel
        )

        # Player 1 cube counter (8 symbols)
        self.player1_cube_symbols = []
        symbol_spacing = 0.08
        symbol_start = LEFT_PANEL_CENTER - (3.5 * symbol_spacing)
        for i in range(8):
            symbol = DirectFrame(
                frameColor=(1, 0.3, 0.3, 1),
                frameSize=(-0.025, 0.025, -0.025, 0.025),
                pos=(symbol_start + i * symbol_spacing, 0, 0.83),
                parent=self.left_panel
            )
            self.player1_cube_symbols.append(symbol)

        # Calculate slot dimensions: 3 equal square slots spanning the panel width
        panel_width = LEFT_PANEL_RIGHT - LEFT_PANEL_LEFT
        slot_width = panel_width / 3
        slot_half = slot_width / 2
        # Scale silhouette so its height (4 face_sizes) fills 85% of the slot
        silhouette_scale = slot_width * 0.85 / (4 * 0.08)
        face_size = 0.08 * silhouette_scale

        # Open (under-construction) slot counts per player
        self.player1_open_slots = PLAYER_START_OPEN_CUBES
        self.player2_open_slots = PLAYER_START_OPEN_CUBES

        # Selection state for cube slots
        self.selected_p1_cube = None
        self.selected_p2_cube = None

        # Player 1 cube silhouettes (3 individual selectable slots)
        self.player1_cube_slots = []
        self.player1_cube_containers = []
        for i in range(3):
            slot_x = LEFT_PANEL_LEFT + slot_half + i * slot_width
            is_open = (i < self.player1_open_slots)
            bg_color = (0.08, 0.08, 0.1, 1.0) if is_open else (0.04, 0.04, 0.05, 1.0)
            slot_btn = DirectButton(
                frameColor=bg_color,
                frameSize=(-slot_half, slot_half, -slot_half, slot_half),
                pos=(slot_x, 0, 0.5),
                command=self.on_select_cube,
                extraArgs=['p1', i],
                parent=self.left_panel,
                rolloverSound=None,
                clickSound=None,
                relief=DGG.FLAT,
            )
            self.player1_cube_slots.append(slot_btn)
            # Offset container up by half a face_size to center the cross pattern vertically
            container = slot_btn.attachNewNode(f"player1_cube_{i}")
            container.setPos(0, 0, 0.5 * face_size)
            self.player1_cube_containers.append(container)
            if is_open:
                self.display_flattened_cube(container, None, scale=silhouette_scale)

        # Player 2 section (BLUE - bottom half)
        player2_label = DirectLabel(
            text="Player 2",
            text_scale=0.07,
            text_fg=(0.3, 0.3, 1, 1),
            text_align=TextNode.ACenter,
            frameColor=(0, 0, 0, 0),
            pos=(LEFT_PANEL_CENTER, 0, -0.08),
            parent=self.left_panel
        )

        # Player 2 cube silhouettes (3 individual selectable slots)
        self.player2_cube_slots = []
        self.player2_cube_containers = []
        for i in range(3):
            slot_x = LEFT_PANEL_LEFT + slot_half + i * slot_width
            is_open = (i < self.player2_open_slots)
            bg_color = (0.08, 0.08, 0.1, 1.0) if is_open else (0.04, 0.04, 0.05, 1.0)
            slot_btn = DirectButton(
                frameColor=bg_color,
                frameSize=(-slot_half, slot_half, -slot_half, slot_half),
                pos=(slot_x, 0, -0.5),
                command=self.on_select_cube,
                extraArgs=['p2', i],
                parent=self.left_panel,
                rolloverSound=None,
                clickSound=None,
                relief=DGG.FLAT,
            )
            self.player2_cube_slots.append(slot_btn)
            container = slot_btn.attachNewNode(f"player2_cube_{i}")
            container.setPos(0, 0, 0.5 * face_size)
            self.player2_cube_containers.append(container)
            if is_open:
                self.display_flattened_cube(container, None, scale=silhouette_scale)

        # Player 2 cube counter (8 symbols) - at very bottom
        self.player2_cube_symbols = []
        for i in range(8):
            symbol = DirectFrame(
                frameColor=(0.3, 0.3, 1, 1),
                frameSize=(-0.025, 0.025, -0.025, 0.025),
                pos=(symbol_start + i * symbol_spacing, 0, -0.95),
                parent=self.left_panel
            )
            self.player2_cube_symbols.append(symbol)

        # Right panel background
        self.panel = DirectFrame(
            frameColor=(0.15, 0.15, 0.18, 1.0),
            frameSize=(RIGHT_PANEL_LEFT, RIGHT_PANEL_RIGHT, -1, 1),
            pos=(0, 0, 0)
        )

        # Calculate right panel relative sizes
        right_panel_width = RIGHT_PANEL_RIGHT - RIGHT_PANEL_LEFT
        right_panel_padding = right_panel_width * 0.08
        right_content_width = right_panel_width - (2 * right_panel_padding)

        # Title
        title = DirectLabel(
            text="Cube Roller",
            text_scale=right_panel_width * 0.1,
            text_fg=(1, 1, 1, 1),
            text_align=TextNode.ACenter,
            frameColor=(0, 0, 0, 0),
            pos=(RIGHT_PANEL_CENTER, 0, 0.9),
            parent=self.panel
        )

        # Info text
        self.info_label = DirectLabel(
            text="Click a cube to select",
            text_scale=right_panel_width * 0.06,
            text_fg=(0.9, 0.9, 0.9, 1),
            text_align=TextNode.ACenter,
            frameColor=(0, 0, 0, 0),
            pos=(RIGHT_PANEL_CENTER, 0, 0.8),
            text_wordwrap=15,
            parent=self.panel
        )

        # Unfolded cube display area
        cube_display_label = DirectLabel(
            text="Selected Cube:",
            text_scale=right_panel_width * 0.065,
            text_fg=(1, 1, 1, 1),
            text_align=TextNode.ACenter,
            frameColor=(0, 0, 0, 0),
            pos=(RIGHT_PANEL_CENTER, 0, 0.65),
            parent=self.panel
        )

        # Dark subwindow for unfolded cube - sized relative to panel
        # Cube silhouette needs 3 faces wide, 4 faces tall
        cube_frame_width = right_content_width * 0.9
        cube_frame_height = cube_frame_width * 1.3  # Taller than wide for cross pattern
        self.cube_display_frame = DirectFrame(
            frameColor=(0.08, 0.08, 0.1, 1.0),
            frameSize=(-cube_frame_width/2, cube_frame_width/2, -cube_frame_height/2, cube_frame_height/2),
            pos=(RIGHT_PANEL_CENTER, 0, 0.25),
            parent=self.panel
        )

        # Calculate silhouette scale to fit in frame (face_size base is 0.12)
        # Cross pattern is 3 faces wide, 4 faces tall - use smaller of width/height constraints
        scale_by_width = (cube_frame_width / 3) / 0.12
        scale_by_height = (cube_frame_height / 4) / 0.12
        self.right_silhouette_scale = min(scale_by_width, scale_by_height) * 0.85  # 85% for padding

        # Container for unfolded cube display
        self.unfolded_cube_container = self.aspect2d.attachNewNode("unfoldedCubeContainer")
        self.unfolded_cube_container.setPos(RIGHT_PANEL_CENTER, 0, 0.25)

        # Action buttons
        button_y = -0.2
        button_spacing = 0.12
        button_width = right_content_width * 0.45

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
                text_scale=right_panel_width * 0.055,
                text_fg=(1, 1, 1, 1),
                frameColor=(0.3, 0.4, 0.5, 1),
                frameSize=(-button_width, button_width, -0.04, 0.04),
                pos=(RIGHT_PANEL_CENTER, 0, button_y - i * button_spacing),
                command=command,
                parent=self.panel,
                rolloverSound=None,
                clickSound=None,
            )
            self.action_buttons.append(btn)

        # Instructions - moved inside the cube display frame at the bottom
        instructions = DirectLabel(
            text="Arrow Keys: Rotate\n+/- : Zoom\nR: Reset camera",
            text_scale=right_panel_width * 0.038,
            text_fg=(0.45, 0.45, 0.45, 1),
            text_align=TextNode.ACenter,
            frameColor=(0, 0, 0, 0),
            pos=(RIGHT_PANEL_CENTER, 0, 0.25 - cube_frame_height * 0.40),
            text_wordwrap=15,
            parent=self.panel
        )

        # Turn indicator at the bottom of the right panel
        DirectLabel(
            text="Turn",
            text_scale=right_panel_width * 0.05,
            text_fg=(0.7, 0.7, 0.7, 1),
            text_align=TextNode.ACenter,
            frameColor=(0, 0, 0, 0),
            pos=(RIGHT_PANEL_CENTER, 0, -0.80),
            parent=self.panel
        )
        circle_r = right_panel_width * 0.065
        self.turn_circle = self._create_circle_np(self.panel, circle_r)
        self.turn_circle.setPos(RIGHT_PANEL_CENTER, 0, -0.89)
        self.turn_circle.setColor(1, 0.3, 0.3, 1)  # P1 red
        self.turn_player_label = DirectLabel(
            text="P1",
            text_scale=right_panel_width * 0.05,
            text_fg=(1, 0.3, 0.3, 1),
            text_align=TextNode.ACenter,
            frameColor=(0, 0, 0, 0),
            pos=(RIGHT_PANEL_CENTER, 0, -0.97),
            parent=self.panel
        )

    def on_mouse_click(self):
        """Handle left mouse click for cube selection"""
        if not self.mouseWatcherNode.hasMouse():
            return

        mpos = self.mouseWatcherNode.getMouse()

        # Cast ray from camera through mouse position
        self.pickerRay.setFromLens(self.camNode, mpos.getX(), mpos.getY())
        self.picker.traverse(self.render)

        if self.pq.getNumEntries() > 0:
            self.pq.sortEntries()
            picked_obj = self.pq.getEntry(0).getIntoNodePath()
            picked_node = picked_obj.findNetTag('name')
            if not picked_node.isEmpty() and picked_node.getTag('type') == 'cube':
                self.select_cube(picked_node)
                return

        # Nothing selected in 3D - request a deselect unless a GUI button cancels it
        self._deselect_pending = True

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

    def deselect_all(self):
        """Deselect everything and close all menus"""
        self.deselect_cube()
        normal_color = (0.08, 0.08, 0.1, 1.0)
        if self.selected_p1_cube is not None:
            self.player1_cube_slots[self.selected_p1_cube]['frameColor'] = normal_color
            self.selected_p1_cube = None
        if self.selected_p2_cube is not None:
            self.player2_cube_slots[self.selected_p2_cube]['frameColor'] = normal_color
            self.selected_p2_cube = None
        self.hide_roll_menu()
        self.hide_add_side_menu()

    def _process_pending_deselect(self, task):
        """Task (sort=200): runs after all event handlers each frame.
        Deselects everything if on_mouse_click found nothing and no GUI button cancelled it."""
        if self._deselect_pending and not self._gui_button_clicked:
            self.deselect_all()
        self._deselect_pending = False
        self._gui_button_clicked = False
        return task.cont

    def clear_unfolded_cube(self):
        """Clear the unfolded cube display"""
        self.unfolded_cube_container.removeNode()
        self.unfolded_cube_container = self.aspect2d.attachNewNode("unfoldedCubeContainer")
        self.unfolded_cube_container.setPos(RIGHT_PANEL_CENTER, 0, 0.25)

    def display_unfolded_cube(self, cube_data):
        """Display the selected cube in unfolded (cross) format"""
        # Clear previous display
        self.clear_unfolded_cube()

        # Face size for display - scaled to fit frame
        face_size = 0.12 * self.right_silhouette_scale

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
        # Offset by face_size/2 to center vertically (pattern spans +face_size to -2*face_size)
        z_offset = face_size / 2

        face_positions = {
            'top': (0, 0, z_offset),
            'back': (0, 0, face_size + z_offset),
            'bottom': (0, 0, -2 * face_size + z_offset),
            'left': (-face_size, 0, z_offset),
            'right': (face_size, 0, z_offset),
            'front': (0, 0, -face_size + z_offset),
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

    def _create_circle_np(self, parent, radius, segments=32):
        """Create a filled circle NodePath in the XZ plane, suitable for aspect2d."""
        vdata = GeomVertexData('circle', GeomVertexFormat.getV3(), Geom.UHStatic)
        vdata.setNumRows(segments + 1)
        writer = GeomVertexWriter(vdata, 'vertex')
        writer.addData3f(0, 0, 0)
        for i in range(segments):
            a = 2 * math.pi * i / segments
            writer.addData3f(math.cos(a) * radius, 0, math.sin(a) * radius)
        tris = GeomTriangles(Geom.UHStatic)
        for i in range(segments):
            tris.addVertices(0, i + 1, (i + 1) % segments + 1)
        tris.closePrimitive()
        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode('turn_circle')
        node.addGeom(geom)
        np = parent.attachNewNode(node)
        np.setTwoSided(True)
        np.setDepthTest(False)
        np.setDepthWrite(False)
        return np

    def set_current_player(self, player):
        """Switch the active turn to player 1 or 2 and update the indicator."""
        self.current_player = player
        if player == 1:
            self.turn_circle.setColor(1, 0.3, 0.3, 1)
            self.turn_player_label['text'] = 'P1'
            self.turn_player_label['text_fg'] = (1, 0.3, 0.3, 1)
            if self.selected_p2_cube is not None:
                self.player2_cube_slots[self.selected_p2_cube]['frameColor'] = (0.08, 0.08, 0.1, 1.0)
                self.selected_p2_cube = None
        else:
            self.turn_circle.setColor(0.3, 0.3, 1, 1)
            self.turn_player_label['text'] = 'P2'
            self.turn_player_label['text_fg'] = (0.3, 0.3, 1, 1)
            if self.selected_p1_cube is not None:
                self.player1_cube_slots[self.selected_p1_cube]['frameColor'] = (0.08, 0.08, 0.1, 1.0)
                self.selected_p1_cube = None

    def on_select_cube(self, player, index):
        """Handle cube silhouette slot selection in the left panel"""
        self._gui_button_clicked = True
        # Restrict to the player whose turn it is
        if (player == 'p1' and self.current_player != 1) or \
           (player == 'p2' and self.current_player != 2):
            return
        # Ignore clicks on locked (not yet open) slots
        open_count = self.player1_open_slots if player == 'p1' else self.player2_open_slots
        if index >= open_count:
            return

        normal_color = (0.08, 0.08, 0.1, 1.0)
        if player == 'p1':
            slots = self.player1_cube_slots
            highlight_color = (0.22, 0.12, 0.10, 1.0)
            current = self.selected_p1_cube
            if current == index:
                slots[index]['frameColor'] = normal_color
                self.selected_p1_cube = None
            else:
                if current is not None:
                    slots[current]['frameColor'] = normal_color
                slots[index]['frameColor'] = highlight_color
                self.selected_p1_cube = index
        else:
            slots = self.player2_cube_slots
            highlight_color = (0.10, 0.12, 0.22, 1.0)
            current = self.selected_p2_cube
            if current == index:
                slots[index]['frameColor'] = normal_color
                self.selected_p2_cube = None
            else:
                if current is not None:
                    slots[current]['frameColor'] = normal_color
                slots[index]['frameColor'] = highlight_color
                self.selected_p2_cube = index

    def setup_roll_menu(self):
        """Setup the roll direction menu (initially hidden)"""
        # Container for roll menu at bottom center of game area
        self.roll_menu = DirectFrame(
            frameColor=(0.1, 0.1, 0.12, 0.9),
            frameSize=(-0.44, 0.44, -0.06, 0.06),
            pos=(GAME_AREA_CENTER, 0, -0.85)
        )
        self.roll_menu.hide()

        # Button size and spacing
        btn_size = 0.045
        btn_frame = (-btn_size, btn_size, -btn_size, btn_size)
        spacing = 0.11

        # Track selected direction
        self.selected_roll_direction = None
        self.ability_triggered = False

        # Button colors
        self.btn_normal_color = (0.25, 0.3, 0.35, 1)
        self.btn_pressed_color = (0.15, 0.18, 0.22, 1)

        # Buttons: <, ^, v, >, A (ability), OK (confirm), X (cancel)
        roll_buttons = [
            ("<", "left", -3 * spacing),
            ("^", "up", -2 * spacing),
            ("v", "down", -1 * spacing),
            (">", "right", 0 * spacing),
            ("A", "ability", 1 * spacing),
            ("OK", "confirm", 2 * spacing),
            ("X", "cancel", 3 * spacing),
        ]

        self.roll_buttons = {}
        for symbol, name, x_pos in roll_buttons:
            btn = DirectButton(
                text=symbol,
                text_scale=0.05,
                text_fg=(1, 1, 1, 1),
                frameColor=self.btn_normal_color,
                frameSize=btn_frame,
                pos=(x_pos, 0, 0),
                command=self.on_roll_button_click,
                extraArgs=[name],
                parent=self.roll_menu,
                rolloverSound=None,
                clickSound=None,
            )
            self.roll_buttons[name] = btn

    def show_roll_menu(self):
        """Show the roll direction menu"""
        # Reset button states
        self.selected_roll_direction = None
        self.ability_triggered = False
        for btn in self.roll_buttons.values():
            btn['frameColor'] = self.btn_normal_color
        self.roll_menu.show()

    def hide_roll_menu(self):
        """Hide the roll direction menu"""
        self.roll_menu.hide()

    def on_roll_button_click(self, button_name):
        """Handle roll menu button clicks with toggle behavior"""
        self._gui_button_clicked = True
        if button_name in ["left", "up", "down", "right"]:
            # Direction buttons - only one can be selected
            if self.selected_roll_direction == button_name:
                # Deselect if clicking same button
                self.roll_buttons[button_name]['frameColor'] = self.btn_normal_color
                self.selected_roll_direction = None
                self.info_label['text'] = "Select roll direction"
            else:
                # Deselect previous direction
                if self.selected_roll_direction:
                    self.roll_buttons[self.selected_roll_direction]['frameColor'] = self.btn_normal_color
                # Select new direction
                self.roll_buttons[button_name]['frameColor'] = self.btn_pressed_color
                self.selected_roll_direction = button_name
                self.info_label['text'] = f"Roll {button_name}"

        elif button_name == "ability":
            # Toggle ability
            self.ability_triggered = not self.ability_triggered
            if self.ability_triggered:
                self.roll_buttons["ability"]['frameColor'] = self.btn_pressed_color
                self.info_label['text'] = "Ability will trigger"
            else:
                self.roll_buttons["ability"]['frameColor'] = self.btn_normal_color
                self.info_label['text'] = "Ability disabled"

        elif button_name == "confirm":
            if self.selected_roll_direction:
                self.info_label['text'] = f"Rolled {self.selected_roll_direction}!"
                self.hide_roll_menu()
            else:
                self.info_label['text'] = "Select a direction first!"

        elif button_name == "cancel":
            self.info_label['text'] = "Roll cancelled"
            self.hide_roll_menu()

    def on_roll_cube(self):
        """Handle roll cube button"""
        self._gui_button_clicked = True
        if self.selected_cube:
            self.info_label['text'] = "Select roll direction"
            self.show_roll_menu()
        else:
            self.info_label['text'] = "Select a cube first!"

    def setup_add_side_menu(self):
        """Setup the add side menu (initially hidden)"""
        # Effects available (matching icon filenames in assets/icons/)
        self.effects = ["slide", "push", "fortify", "grapple", "detonate",
                        "start", "rotate", "strength", "build", "slash"]

        # Get the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        icons_dir = os.path.join(script_dir, "..", "assets", "icons")

        # Container for add side menu at bottom center of game area (three rows)
        self.add_side_menu = DirectFrame(
            frameColor=(0.1, 0.1, 0.12, 0.9),
            frameSize=(-0.30, 0.30, -0.23, 0.12),
            pos=(GAME_AREA_CENTER, 0, -0.75)
        )
        self.add_side_menu.hide()

        # Button size and spacing
        btn_size = 0.05
        btn_frame = (-btn_size, btn_size, -btn_size, btn_size)
        spacing = 0.11

        # Track selected effect
        self.selected_effect = None

        # Create effect buttons in two rows (5 per row + OK/X on second row)
        self.effect_buttons = {}
        img_scale = btn_size * 0.9  # Image scale slightly smaller than button

        # First row: first 5 effects
        for i, effect in enumerate(self.effects[:5]):
            x_pos = (i - 2) * spacing
            icon_path = os.path.join(icons_dir, f"{effect}.png")
            btn = DirectButton(
                image=icon_path,
                image_scale=img_scale,
                frameColor=self.btn_normal_color,
                frameSize=btn_frame,
                pos=(x_pos, 0, 0.055),
                command=self.on_effect_button_click,
                extraArgs=[effect],
                parent=self.add_side_menu,
                rolloverSound=None,
                clickSound=None,
            )
            self.effect_buttons[effect] = btn

        # Second row: remaining 5 effects
        for i, effect in enumerate(self.effects[5:]):
            x_pos = (i - 2) * spacing
            icon_path = os.path.join(icons_dir, f"{effect}.png")
            btn = DirectButton(
                image=icon_path,
                image_scale=img_scale,
                frameColor=self.btn_normal_color,
                frameSize=btn_frame,
                pos=(x_pos, 0, -0.055),
                command=self.on_effect_button_click,
                extraArgs=[effect],
                parent=self.add_side_menu,
                rolloverSound=None,
                clickSound=None,
            )
            self.effect_buttons[effect] = btn

        # Third row: rotate CW, rotate CCW, OK, X
        # Rotate CW button with icon
        cw_icon_path = os.path.join(icons_dir, "rotate_cw.png")
        cw_btn = DirectButton(
            image=cw_icon_path,
            image_scale=img_scale,
            frameColor=self.btn_normal_color,
            frameSize=btn_frame,
            pos=(-1.5 * spacing, 0, -0.165),
            command=self.on_effect_button_click,
            extraArgs=["rotate_cw"],
            parent=self.add_side_menu,
            rolloverSound=None,
            clickSound=None,
        )
        self.effect_buttons["rotate_cw"] = cw_btn

        # Rotate CCW button (mirrored CW icon)
        ccw_btn = DirectButton(
            image=cw_icon_path,
            image_scale=(-img_scale, img_scale, img_scale),  # Negative x to mirror
            frameColor=self.btn_normal_color,
            frameSize=btn_frame,
            pos=(-0.5 * spacing, 0, -0.165),
            command=self.on_effect_button_click,
            extraArgs=["rotate_ccw"],
            parent=self.add_side_menu,
            rolloverSound=None,
            clickSound=None,
        )
        self.effect_buttons["rotate_ccw"] = ccw_btn

        # OK button
        ok_btn = DirectButton(
            text="OK",
            text_scale=0.04,
            text_fg=(1, 1, 1, 1),
            frameColor=self.btn_normal_color,
            frameSize=btn_frame,
            pos=(0.5 * spacing, 0, -0.165),
            command=self.on_effect_button_click,
            extraArgs=["confirm"],
            parent=self.add_side_menu,
            rolloverSound=None,
            clickSound=None,
        )
        self.effect_buttons["confirm"] = ok_btn

        # X (cancel) button
        cancel_btn = DirectButton(
            text="X",
            text_scale=0.04,
            text_fg=(1, 1, 1, 1),
            frameColor=self.btn_normal_color,
            frameSize=btn_frame,
            pos=(1.5 * spacing, 0, -0.165),
            command=self.on_effect_button_click,
            extraArgs=["cancel"],
            parent=self.add_side_menu,
            rolloverSound=None,
            clickSound=None,
        )
        self.effect_buttons["cancel"] = cancel_btn

    def show_add_side_menu(self):
        """Show the add side menu"""
        self.selected_effect = None
        self.selected_rotation = None
        for name, btn in self.effect_buttons.items():
            if name not in ["confirm", "cancel"]:
                btn['frameColor'] = self.btn_normal_color
        self.add_side_menu.show()

    def hide_add_side_menu(self):
        """Hide the add side menu"""
        self.add_side_menu.hide()

    def on_effect_button_click(self, effect_name):
        """Handle effect button clicks"""
        self._gui_button_clicked = True
        if effect_name in self.effects:
            # Effect buttons - only one can be selected
            if self.selected_effect == effect_name:
                # Deselect if clicking same button
                self.effect_buttons[effect_name]['frameColor'] = self.btn_normal_color
                self.selected_effect = None
                self.info_label['text'] = "Select an effect"
            else:
                # Deselect previous effect
                if self.selected_effect:
                    self.effect_buttons[self.selected_effect]['frameColor'] = self.btn_normal_color
                # Select new effect
                self.effect_buttons[effect_name]['frameColor'] = self.btn_pressed_color
                self.selected_effect = effect_name
                self.info_label['text'] = f"Selected: {effect_name}"

        elif effect_name == "rotate_cw":
            # Rotate clockwise - just set direction, don't toggle
            self.selected_rotation = "cw"
            rot_text = "clockwise" if self.selected_effect else "Select an effect first"
            self.info_label['text'] = f"Rotation: {rot_text}"

        elif effect_name == "rotate_ccw":
            # Rotate counter-clockwise - just set direction, don't toggle
            self.selected_rotation = "ccw"
            rot_text = "counter-clockwise" if self.selected_effect else "Select an effect first"
            self.info_label['text'] = f"Rotation: {rot_text}"

        elif effect_name == "confirm":
            if self.selected_effect:
                rot_text = ""
                if self.selected_rotation:
                    rot_text = " (CW)" if self.selected_rotation == "cw" else " (CCW)"
                self.info_label['text'] = f"Added {self.selected_effect}{rot_text} side!"
                self.hide_add_side_menu()
            else:
                self.info_label['text'] = "Select an effect first!"

        elif effect_name == "cancel":
            self.info_label['text'] = "Add side cancelled"
            self.hide_add_side_menu()

    def on_build_cube(self):
        """Handle build new cube button"""
        self._gui_button_clicked = True
        self.info_label['text'] = "Building new cube... (not implemented)"

    def on_add_side(self):
        """Handle add side button"""
        self._gui_button_clicked = True
        if self.selected_p1_cube is not None or self.selected_p2_cube is not None:
            self.info_label['text'] = "Select an effect"
            self.show_add_side_menu()
        else:
            self.info_label['text'] = "Select a cube under construction first!"

    def on_end_turn(self):
        """Handle end turn button"""
        self._gui_button_clicked = True
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
