from direct.showbase.ShowBase import ShowBase
from panda3d.core import *
from direct.gui.DirectGui import *
from direct.gui import DirectGuiGlobals as DGG
from direct.task import Task
from direct.interval.IntervalGlobal import LerpPosInterval, LerpHprInterval, Parallel, Func, Sequence
import sys
import random
import os
import math

from main import Board, Cube, Player, dir_to_coords

# Face name mapping between GUI and main.py logic
FACE_GUI_TO_LOGIC = {'top': 'u', 'front': 'f', 'bottom': 'd', 'back': 'b', 'left': 'l', 'right': 'r'}
FACE_LOGIC_TO_GUI = {v: k for k, v in FACE_GUI_TO_LOGIC.items()}

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

        # Initialize game logic
        # Note: Player.__init__ has a bug in factory grid marking when factory coords exceed grid bounds.
        # Work around by creating players with empty factories, then assigning manually.
        self.board = Board(width=5, height=7, exclusions=[0, 1, 4])
        self.player1 = Player("1", self.board, factories=[])
        self.player1.factories = [(0, 2), (0, 3)]   # (y, x) tuples: row 0, cols 2 and 3
        self.player2 = Player("2", self.board, factories=[])
        self.player2.factories = [(6, 1), (6, 2)]   # (y, x) tuples: row 6, cols 1 and 2

        self.deploy_mode = False
        self.deploy_cube_index = None
        self.rolling = False
        self.build_display_rotations = []  # temporary cube rotations during build mode
        self.unfolded_face_nodes = {}      # face_name -> NodePath for highlight
        self.unfolded_face_bounds = {}     # face_name -> (cx, cz, half_size) for hit testing

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

        # Deferred deselect: set by on_mouse_click, cancelled by any GUI button handler.
        # A task running at sort=200 (after the event manager) checks both flags.
        self._deselect_pending = False
        self._gui_button_clicked = False
        self.taskMgr.add(self._process_pending_deselect, 'process_pending_deselect', sort=200)
        self._update_action_buttons()

    # ─── Game Logic Helpers ──────────────────────────────────────────────────

    def cube_to_icon_list(self, cube):
        """Convert a main.py Cube to [(effect_name, gui_face_name), ...] for display."""
        sides = [
            (cube.u, 'top'), (cube.f, 'front'), (cube.d, 'bottom'),
            (cube.b, 'back'), (cube.l, 'left'), (cube.r, 'right'),
        ]
        return [(side.effect if side.effect else 'empty', face) for side, face in sides]

    def is_roll_legal(self, x, y, direction):
        """Check if rolling from (x, y) in direction is legal (bounds + occupancy)."""
        dx, dy = dir_to_coords[direction]
        nx, ny = x + dx, y + dy
        if nx < 0 or nx >= self.board.width or ny < 0 or ny >= self.board.height:
            return False
        if self.board.grid[ny][nx] is not None:
            return False
        return True

    def end_turn(self):
        """End current player's turn and switch to other player."""
        next_player = 2 if self.current_player == 1 else 1
        self.set_current_player(next_player)
        self.deselect_all()
        self.update_cube_counters(len(self.player1.cubes), len(self.player2.cubes))
        self.info_label['text'] = f"Player {next_player}'s turn"
        self._update_action_buttons()

    # ─── Scene ───────────────────────────────────────────────────────────────

    def setup_scene(self):
        """Create the game board"""
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

    def create_cube(self, board_x, board_y, cube_logic):
        """Create a 3D cube from a Cube logic object. Returns (cube_node, face_nodes)."""
        cube = self.render.attachNewNode("cube")

        # Derive icon faces from cube logic
        icon_faces = self.cube_to_icon_list(cube_logic)

        # Load available icons
        icon_dict = {}
        for effect, face in icon_faces:
            if effect and effect != 'empty':
                icon_path = f"../assets/icons/{effect}.png"
                try:
                    tex = self.loader.loadTexture(icon_path)
                    tex.setMinfilter(Texture.FTLinearMipmapLinear)
                    tex.setMagfilter(Texture.FTLinear)
                    icon_dict[face] = tex
                except:
                    print(f"Warning: Could not load texture {icon_path}")

        # size is half the cube's side length
        size = 0.4

        # CardMaker creates cards in XY plane facing +Z
        faces_config = [
            # (name, position, heading, pitch, roll)
            ('top',    (0, 0, size),   0, -90, 180),
            ('bottom', (0, 0, -size),  0,  90, 180),
            ('front',  (0, size, 0),  180,   0,   0),
            ('back',   (0, -size, 0),   0,   0, 180),
            ('right',  (size, 0, 0),   90,   0, -90),
            ('left',   (-size, 0, 0), -90,   0,  90),
        ]

        face_nodes = {}
        for face_name, pos, h, p, r in faces_config:
            cm = CardMaker(f"face_{face_name}")
            cm.setFrame(-size, size, -size, size)
            face = cube.attachNewNode(cm.generate())
            face.setPos(*pos)
            face.setHpr(h, p, r)
            face_nodes[face_name] = face

            if face_name in icon_dict:
                face.setTexture(icon_dict[face_name])
                face.setColor(1, 1, 1, 1)
            else:
                face.setColor(0.6, 0.6, 0.7, 1)

        # Position cube on board
        world_x = (board_x - self.board_dim[0] / 2) * 1.1
        world_y = (board_y - self.board_dim[1] / 2) * 1.1
        cube.setPos(world_x, world_y, size + 0.05)

        # Add collision detection
        self.add_collision(cube, f'cube_{board_x}_{board_y}')
        cube.setTag('name', f'Cube ({board_x},{board_y})')
        cube.setTag('type', 'cube')

        return cube, face_nodes

    def update_cube_face_textures(self, cube_data):
        """Re-apply textures to face nodes based on current Cube logic state."""
        icon_list = self.cube_to_icon_list(cube_data['logic'])
        icon_dict = {face: effect for effect, face in icon_list}
        for face_name, face_np in cube_data['face_nodes'].items():
            effect = icon_dict.get(face_name)
            if effect and effect != 'empty':
                icon_path = f"../assets/icons/{effect}.png"
                try:
                    tex = self.loader.loadTexture(icon_path)
                    face_np.setTexture(tex)
                    face_np.setColor(1, 1, 1, 1)
                except:
                    face_np.clearTexture()
                    face_np.setColor(0.6, 0.6, 0.7, 1)
            else:
                face_np.clearTexture()
                face_np.setColor(0.6, 0.6, 0.7, 1)

    def add_collision(self, node, name):
        """Add collision detection to an object"""
        bounds = node.getBounds()
        center = bounds.getCenter()
        radius = bounds.getRadius()

        collision_node = CollisionNode(name)
        collision_node.addSolid(CollisionSphere(center, radius))
        collision_np = node.attachNewNode(collision_node)

    # ─── Animation ───────────────────────────────────────────────────────────

    def animate_roll(self, cube_data, direction, on_done):
        """Animate cube rolling 90° in direction, then call on_done().
        Rotation axes may need visual tuning — adjust hpr_deltas if the roll looks wrong."""
        node = cube_data['node']
        dx, dy = dir_to_coords[direction]
        world_dx = dx * 1.1
        world_dy = dy * 1.1

        cur_pos = node.getPos()
        target_pos = Point3(cur_pos.x + world_dx, cur_pos.y + world_dy, cur_pos.z)

        # HPR deltas for a 90° roll in each direction.
        # right/left roll around Y axis (R), up/down roll around X axis (P).
        hpr_deltas = {
            'right': (0,   0, -90),
            'left':  (0,   0,  90),
            'down':  (0, -90,   0),
            'up':    (0,  90,   0),
        }
        dh, dp, dr = hpr_deltas[direction]
        cur_hpr = node.getHpr()
        target_hpr = Point3(cur_hpr.x + dh, cur_hpr.y + dp, cur_hpr.z + dr)

        duration = 0.3
        pos_interval = LerpPosInterval(node, duration, target_pos, startPos=cur_pos)
        hpr_interval = LerpHprInterval(node, duration, target_hpr, startHpr=cur_hpr)

        def finish():
            node.setHpr(0, 0, 0)
            on_done()

        anim = Sequence(
            Parallel(pos_interval, hpr_interval),
            Func(finish)
        )
        anim.start()

    # ─── Lighting ────────────────────────────────────────────────────────────

    def setup_lighting(self):
        """Setup scene lighting"""
        alight = AmbientLight('alight')
        alight.setColor((0.5, 0.5, 0.5, 1))
        alnp = self.render.attachNewNode(alight)
        self.render.setLight(alnp)

        dlight = DirectionalLight('dlight')
        dlight.setColor((0.7, 0.7, 0.7, 1))
        dlnp = self.render.attachNewNode(dlight)
        dlnp.setHpr(45, -60, 0)
        self.render.setLight(dlnp)

        dlight2 = DirectionalLight('dlight2')
        dlight2.setColor((0.3, 0.3, 0.3, 1))
        dlnp2 = self.render.attachNewNode(dlight2)
        dlnp2.setHpr(-135, -45, 0)
        self.render.setLight(dlnp2)

    # ─── Controls ────────────────────────────────────────────────────────────

    def setup_controls(self):
        """Setup keyboard and mouse controls"""
        self.accept('mouse1', self.on_mouse_click)
        self.accept('escape', sys.exit)
        self.accept('r', self.reset_camera)
        self.accept('arrow_left', self.rotate_left)
        self.accept('arrow_right', self.rotate_right)
        self.accept('arrow_up', self.rotate_up)
        self.accept('arrow_down', self.rotate_down)
        self.accept('+', self.zoom_in)
        self.accept('-', self.zoom_out)
        self.accept('=', self.zoom_in)

    # ─── UI ──────────────────────────────────────────────────────────────────

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
        silhouette_scale = slot_width * 0.85 / (4 * 0.08)
        face_size = 0.08 * silhouette_scale

        # Open (under-construction) slot counts per player
        self.player1_open_slots = PLAYER_START_OPEN_CUBES
        self.player2_open_slots = PLAYER_START_OPEN_CUBES

        # Pre-populate cubes so visual slot indices match player.cubes indices
        for _ in range(PLAYER_START_OPEN_CUBES):
            self.player1.add_new_cube()
            self.player2.add_new_cube()

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

        # Player 2 cube counter (8 symbols)
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

        right_panel_width = RIGHT_PANEL_RIGHT - RIGHT_PANEL_LEFT
        right_panel_padding = right_panel_width * 0.08
        right_content_width = right_panel_width - (2 * right_panel_padding)

        title = DirectLabel(
            text="Cube Roller",
            text_scale=right_panel_width * 0.1,
            text_fg=(1, 1, 1, 1),
            text_align=TextNode.ACenter,
            frameColor=(0, 0, 0, 0),
            pos=(RIGHT_PANEL_CENTER, 0, 0.9),
            parent=self.panel
        )

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

        cube_display_label = DirectLabel(
            text="Selected Cube:",
            text_scale=right_panel_width * 0.065,
            text_fg=(1, 1, 1, 1),
            text_align=TextNode.ACenter,
            frameColor=(0, 0, 0, 0),
            pos=(RIGHT_PANEL_CENTER, 0, 0.65),
            parent=self.panel
        )

        cube_frame_width = right_content_width * 0.9
        cube_frame_height = cube_frame_width * 1.3
        self.cube_display_frame = DirectFrame(
            frameColor=(0.08, 0.08, 0.1, 1.0),
            frameSize=(-cube_frame_width/2, cube_frame_width/2, -cube_frame_height/2, cube_frame_height/2),
            pos=(RIGHT_PANEL_CENTER, 0, 0.25),
            parent=self.panel
        )

        scale_by_width = (cube_frame_width / 3) / 0.12
        scale_by_height = (cube_frame_height / 4) / 0.12
        self.right_silhouette_scale = min(scale_by_width, scale_by_height) * 0.85

        # Parent to cube_display_frame so cards render on top of its dark background
        self.unfolded_cube_container = self.cube_display_frame.attachNewNode("unfoldedCubeContainer")
        self.unfolded_cube_container.setPos(0, 0, 0)

        button_y = -0.2
        button_spacing = 0.12
        button_width = right_content_width * 0.45

        buttons = [
            ("Roll Cube",   self.on_roll_cube),
            ("Build New",   self.on_build_cube),
            ("Add Side",    self.on_add_side),
            ("Deploy Cube", self.on_deploy_cube),
            ("End Turn",    self.on_end_turn),
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
        self.turn_circle.setColor(1, 0.3, 0.3, 1)
        self.turn_player_label = DirectLabel(
            text="P1",
            text_scale=right_panel_width * 0.05,
            text_fg=(1, 0.3, 0.3, 1),
            text_align=TextNode.ACenter,
            frameColor=(0, 0, 0, 0),
            pos=(RIGHT_PANEL_CENTER, 0, -0.97),
            parent=self.panel
        )

    # ─── Mouse / Selection ───────────────────────────────────────────────────

    def on_mouse_click(self):
        """Handle left mouse click for cube selection and deploy mode"""
        if not self.mouseWatcherNode.hasMouse():
            return

        if self.rolling:
            return

        mpos = self.mouseWatcherNode.getMouse()

        # Deploy mode: project ray onto board plane (Z=0) and detect grid tile
        if self.deploy_mode:
            self._gui_button_clicked = True
            self.pickerRay.setFromLens(self.camNode, mpos.getX(), mpos.getY())
            p_from = self.render.getRelativePoint(self.cam, self.pickerRay.getOrigin())
            p_dir  = self.render.getRelativeVector(self.cam, self.pickerRay.getDirection())
            if abs(p_dir.z) > 0.001:
                t = -p_from.z / p_dir.z
                world_x = p_from.x + t * p_dir.x
                world_y = p_from.y + t * p_dir.y
                grid_x = int(round(world_x / 1.1 + self.board_dim[0] / 2))
                grid_y = int(round(world_y / 1.1 + self.board_dim[1] / 2))
                self._handle_deploy_click(grid_x, grid_y)
            return

        # Cast ray from camera through mouse position for cube selection
        self.pickerRay.setFromLens(self.camNode, mpos.getX(), mpos.getY())
        self.picker.traverse(self.render)

        if self.pq.getNumEntries() > 0:
            self.pq.sortEntries()
            picked_obj = self.pq.getEntry(0).getIntoNodePath()
            picked_node = picked_obj.findNetTag('name')
            if not picked_node.isEmpty() and picked_node.getTag('type') == 'cube':
                self.select_cube(picked_node)
                return

        # Check if click lands on a face of the right-panel unfolded cube (build mode)
        if not self.add_side_menu.isHidden():
            face = self._hit_test_unfolded_cube()
            if face is not None:
                self.on_face_card_click(face)
                return

        # Prevent stray clicks in the right panel from deselecting everything
        if mpos.getX() * ASPECT_RATIO > RIGHT_PANEL_LEFT:
            return

        # Nothing selected in 3D - request a deselect unless a GUI button cancels it
        self._deselect_pending = True

    def _orient_cube_for_deploy(self, cube):
        """Rotate cube logic so the 'start' face is on the bottom (d) before deploying."""
        if cube.d.effect == 'start':
            pass
        elif cube.b.effect == 'start':
            cube.roll((0, 1))
        elif cube.f.effect == 'start':
            cube.roll((0, -1))
        elif cube.u.effect == 'start':
            cube.roll((0, 1))
            cube.roll((0, 1))
        elif cube.l.effect == 'start':
            cube.rotate('ccw')
        elif cube.r.effect == 'start':
            cube.rotate('cw')

    def _handle_deploy_click(self, grid_x, grid_y):
        """Process a board click while in deploy mode."""
        player = self.player1 if self.current_player == 1 else self.player2
        if 0 <= grid_x < self.board.width and 0 <= grid_y < self.board.height:
            if (grid_y, grid_x) in player.factories:
                if self.board.grid[grid_y][grid_x] is None:
                    cube_idx = self.deploy_cube_index
                    self._orient_cube_for_deploy(player.cubes[cube_idx])
                    player.deploy_cube(cube_idx, grid_x, grid_y)
                    cube_logic = player.cubes[cube_idx]
                    cube_node, face_nodes = self.create_cube(grid_x, grid_y, cube_logic)
                    self.cubes.append({
                        'node': cube_node,
                        'board_pos': (grid_x, grid_y),
                        'logic': cube_logic,
                        'face_nodes': face_nodes,
                    })
                    self.deploy_mode = False
                    self.deploy_cube_index = None
                    self.end_turn()
                else:
                    self.info_label['text'] = "Spawn square is occupied!"
            else:
                self.info_label['text'] = "Must deploy on spawn square!"
        else:
            self.info_label['text'] = "Click a spawn square to deploy!"

    def select_cube(self, cube_node):
        """Select a cube and update UI"""
        if self.selected_cube:
            self.selected_cube.setScale(1, 1, 1)

        self.selected_cube = cube_node
        cube_node.setScale(1.15, 1.15, 1.15)

        name = cube_node.getTag('name')
        cube_data = next((c for c in self.cubes if c['node'] == cube_node), None)

        if cube_data:
            self.info_label['text'] = f"Selected: {name}"
            self.display_unfolded_cube(cube_data)
        else:
            self.info_label['text'] = name
        self._update_action_buttons()

    def deselect_cube(self):
        """Deselect current cube"""
        if self.selected_cube:
            self.selected_cube.setScale(1, 1, 1)
            self.selected_cube = None

        self.info_label['text'] = "Click a cube to select"
        self.clear_unfolded_cube()

    def deselect_all(self):
        """Deselect everything and close all menus"""
        self._undo_build_rotations()
        self.deploy_mode = False
        self.deploy_cube_index = None
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
        self._update_action_buttons()

    # ─── Button State Management ─────────────────────────────────────────────

    def _set_btn_enabled(self, btn, enabled):
        """Enable or visually gray out an action button."""
        if enabled:
            btn['state'] = DGG.NORMAL
            btn.setColorScale(1, 1, 1, 1)
        else:
            btn['state'] = DGG.DISABLED
            btn.setColorScale(0.45, 0.45, 0.45, 0.65)

    def _update_action_buttons(self):
        """Gray out action buttons that are not currently usable."""
        player = self.player1 if self.current_player == 1 else self.player2
        open_slots = self.player1_open_slots if self.current_player == 1 else self.player2_open_slots
        sel_idx = self.selected_p1_cube if self.current_player == 1 else self.selected_p2_cube

        # Roll Cube: requires a deployed cube selected on the board
        can_roll = self.selected_cube is not None

        # Build New: < 3 under construction AND < 8 total cubes ever built
        can_build = open_slots < 3 and len(player.cubes) < 8

        # Add Side: a real under-construction cube slot is selected
        can_add_side = (
            sel_idx is not None
            and sel_idx < len(player.cubes)
            and player.cubes[sel_idx].under_construction
        )

        # Deploy Cube: selected cube is flagged deployable and still under construction
        can_deploy = (
            sel_idx is not None
            and sel_idx < len(player.cubes)
            and player.cubes[sel_idx].under_construction
            and player.cubes[sel_idx].deployable
        )

        # action_buttons: [Roll Cube, Build New, Add Side, Deploy Cube, End Turn]
        self._set_btn_enabled(self.action_buttons[0], can_roll)
        self._set_btn_enabled(self.action_buttons[1], can_build)
        self._set_btn_enabled(self.action_buttons[2], can_add_side)
        self._set_btn_enabled(self.action_buttons[3], can_deploy)
        # End Turn (index 4) is always enabled

    def on_deploy_cube(self):
        """Enter deploy mode for the selected deployable cube."""
        self._gui_button_clicked = True
        player = self.player1 if self.current_player == 1 else self.player2
        sel_idx = self.selected_p1_cube if self.current_player == 1 else self.selected_p2_cube
        if (sel_idx is not None
                and sel_idx < len(player.cubes)
                and player.cubes[sel_idx].deployable):
            self.deploy_mode = True
            self.deploy_cube_index = sel_idx
            self.info_label['text'] = "Click a spawn square to deploy!"
        else:
            self.info_label['text'] = "Select a deployable cube first!"

    def _process_pending_deselect(self, task):
        """Task (sort=200): runs after all event handlers each frame."""
        if self._deselect_pending and not self._gui_button_clicked:
            self.deselect_all()
        self._deselect_pending = False
        self._gui_button_clicked = False
        return task.cont

    # ─── Display Helpers ─────────────────────────────────────────────────────

    def clear_unfolded_cube(self):
        """Clear the unfolded cube display"""
        self.unfolded_cube_container.removeNode()
        self.unfolded_cube_container = self.cube_display_frame.attachNewNode("unfoldedCubeContainer")
        self.unfolded_cube_container.setPos(0, 0, 0)
        self.unfolded_face_nodes = {}
        self.unfolded_face_bounds = {}

    def _hit_test_unfolded_cube(self):
        """Return the face name clicked in the right panel unfolded view, or None."""
        if not self.unfolded_face_bounds or not self.mouseWatcherNode.hasMouse():
            return None
        mpos = self.mouseWatcherNode.getMouse()
        mx = mpos.x * ASPECT_RATIO
        mz = mpos.y
        for face_name, (cx, cz, hs) in self.unfolded_face_bounds.items():
            if abs(mx - cx) < hs and abs(mz - cz) < hs:
                return face_name
        return None

    def _detect_left_panel_face_click(self, player, slot_index):
        """Return a face name if the mouse is over that face in a left-panel silhouette, else None."""
        if not self.mouseWatcherNode.hasMouse():
            return None
        mpos = self.mouseWatcherNode.getMouse()
        mx = mpos.x * ASPECT_RATIO
        mz = mpos.y
        panel_width = LEFT_PANEL_RIGHT - LEFT_PANEL_LEFT
        slot_width = panel_width / 3
        slot_x = LEFT_PANEL_LEFT + slot_width / 2 + slot_index * slot_width
        slot_z = 0.5 if player == 'p1' else -0.5
        scale = slot_width * 0.85 / (4 * 0.08)
        fs = 0.08 * scale
        container_z = slot_z + 0.5 * fs
        face_centers = {
            'top':    (slot_x,      container_z),
            'back':   (slot_x,      container_z + fs),
            'front':  (slot_x,      container_z - fs),
            'bottom': (slot_x,      container_z - 2 * fs),
            'left':   (slot_x - fs, container_z),
            'right':  (slot_x + fs, container_z),
        }
        hs = fs / 2
        for face_name, (fcx, fcz) in face_centers.items():
            if abs(mx - fcx) < hs and abs(mz - fcz) < hs:
                return face_name
        return None

    def _get_current_build_cube(self):
        """Return the Cube logic for the currently selected construction slot, or None."""
        if self.selected_p1_cube is not None and self.selected_p1_cube < len(self.player1.cubes):
            return self.player1.cubes[self.selected_p1_cube]
        if self.selected_p2_cube is not None and self.selected_p2_cube < len(self.player2.cubes):
            return self.player2.cubes[self.selected_p2_cube]
        return None

    def _restore_face_to_base(self, face_name):
        """Restore an unfolded face card to its cube-data appearance (remove preview)."""
        if face_name not in self.unfolded_face_nodes:
            return
        node = self.unfolded_face_nodes[face_name]
        node.setR(0)           # clear effect-direction rotation
        node.clearTexture()
        node.setColor(0.4, 0.4, 0.5, 1)
        # Re-apply actual effect icon if the cube already has one on this face
        cube_logic = self._get_current_build_cube()
        if cube_logic:
            logic_face = FACE_GUI_TO_LOGIC.get(face_name, '')
            if logic_face:
                side = getattr(cube_logic, logic_face, None)
                if side and side.effect:
                    icon_path = f"../assets/icons/{side.effect}.png"
                    try:
                        tex = self.loader.loadTexture(icon_path)
                        node.setTexture(tex)
                        node.setColor(1, 1, 1, 1)
                    except Exception:
                        pass

    def on_face_card_click(self, face_name):
        """Handle a face being clicked on the unfolded cube."""
        self._gui_button_clicked = True
        # Always restore the previously selected face to its base appearance first
        if self.selected_face and self.selected_face in self.unfolded_face_nodes:
            self._restore_face_to_base(self.selected_face)
        if self.selected_face == face_name:
            # Toggle off
            self.selected_face = None
            self.info_label['text'] = "Click a face on the cube"
        else:
            self.selected_face = face_name
            if face_name in self.unfolded_face_nodes:
                self.unfolded_face_nodes[face_name].setColor(0.9, 0.9, 0.3, 1)
            self.info_label['text'] = f"Face: {face_name}"
            self._update_build_preview()

    def _update_build_preview(self):
        """Show the selected effect icon (with current rotation) on the selected face."""
        if not self.selected_face or not self.selected_effect:
            return
        if self.selected_face not in self.unfolded_face_nodes:
            return
        face_node = self.unfolded_face_nodes[self.selected_face]
        icon_path = f"../assets/icons/{self.selected_effect}.png"
        try:
            tex = self.loader.loadTexture(icon_path)
            face_node.setTexture(tex)
            face_node.setColor(1, 1, 0.5, 1)  # yellow tint = preview
        except Exception:
            face_node.setColor(0.9, 0.9, 0.3, 1)
        # Spin the card to show the effect direction
        face_node.setR(getattr(self, 'selected_rotation_deg', 0))

    def _undo_build_rotations(self):
        """Reset build-mode preview state (called on cancel / deselect)."""
        if self.selected_face and self.selected_face in self.unfolded_face_nodes:
            self._restore_face_to_base(self.selected_face)
        self.selected_rotation_deg = 0
        self.build_display_rotations = []

    def display_unfolded_cube(self, cube_data):
        """Display the selected cube in unfolded (cross) format"""
        self.clear_unfolded_cube()
        # clear_unfolded_cube resets these, but be explicit
        self.unfolded_face_nodes = {}
        self.unfolded_face_bounds = {}

        face_size = 0.12 * self.right_silhouette_scale

        # Build icon dict and rotation dict from logic or legacy icons list
        icon_dict = {}
        rot_dict = {}
        if 'logic' in cube_data:
            cube = cube_data['logic']
            rot_dict = {
                'top': cube.u_rot, 'front': cube.f_rot, 'bottom': cube.d_rot,
                'back': cube.b_rot, 'left': cube.l_rot, 'right': cube.r_rot,
            }
            for effect, face in self.cube_to_icon_list(cube):
                if effect and effect != 'empty':
                    icon_path = f"../assets/icons/{effect}.png"
                    try:
                        tex = self.loader.loadTexture(icon_path)
                        icon_dict[face] = tex
                    except:
                        pass
        elif 'icons' in cube_data:
            for icon_name, face in cube_data['icons']:
                icon_path = f"../assets/icons/{icon_name}.png"
                try:
                    tex = self.loader.loadTexture(icon_path)
                    icon_dict[face] = tex
                except:
                    pass

        # Cross layout:
        #       [back]
        # [left][top][right]
        #      [front]
        #     [bottom]
        z_offset = face_size / 2
        face_positions = {
            'top':    (0,           0, z_offset),
            'back':   (0,           0, face_size + z_offset),
            'bottom': (0,           0, -2 * face_size + z_offset),
            'left':   (-face_size,  0, z_offset),
            'right':  (face_size,   0, z_offset),
            'front':  (0,           0, -face_size + z_offset),
        }

        for face_name, (x, y, z) in face_positions.items():
            cm = CardMaker(f"unfolded_{face_name}")
            cm.setFrame(-face_size/2, face_size/2, -face_size/2, face_size/2)
            face = self.unfolded_cube_container.attachNewNode(cm.generate())
            face.setPos(x, y, z)
            if face_name in icon_dict:
                face.setTexture(icon_dict[face_name])
                face.setColor(1, 1, 1, 1)
                face.setR(rot_dict.get(face_name, 0))
            else:
                face.setColor(0.4, 0.4, 0.5, 1)
            # Track for interactive hit-testing and highlighting
            self.unfolded_face_nodes[face_name] = face
            # Absolute aspect2d coords: container is at (RIGHT_PANEL_CENTER, 0, 0.25)
            self.unfolded_face_bounds[face_name] = (RIGHT_PANEL_CENTER + x, 0.25 + z, face_size / 2)

    def update_cube_counters(self, player1_count, player2_count):
        """Update the cube counter displays for both players"""
        for i, symbol in enumerate(self.player1_cube_symbols):
            if i < player1_count:
                symbol['frameColor'] = (1, 0.3, 0.3, 1)
            else:
                symbol['frameColor'] = (0.3, 0.2, 0.2, 0.5)

        for i, symbol in enumerate(self.player2_cube_symbols):
            if i < player2_count:
                symbol['frameColor'] = (0.3, 0.3, 1, 1)
            else:
                symbol['frameColor'] = (0.2, 0.2, 0.3, 0.5)

    def display_flattened_cube(self, container, cube_data, scale=1.0):
        """Display a flattened cube in the given container (cube_data may be None, or
        contain 'logic' (Cube object) or 'icons' (legacy list)."""
        for child in container.getChildren():
            child.removeNode()

        face_size = 0.08 * scale

        face_positions = {
            'top':    (0,          0, 0),
            'back':   (0,          0, face_size),
            'bottom': (0,          0, -2 * face_size),
            'left':   (-face_size, 0, 0),
            'right':  (face_size,  0, 0),
            'front':  (0,          0, -face_size),
        }

        icon_dict = {}
        rot_dict = {}
        if cube_data:
            if 'logic' in cube_data:
                cube = cube_data['logic']
                rot_dict = {
                    'top': cube.u_rot, 'front': cube.f_rot, 'bottom': cube.d_rot,
                    'back': cube.b_rot, 'left': cube.l_rot, 'right': cube.r_rot,
                }
                for effect, face in self.cube_to_icon_list(cube):
                    if effect and effect != 'empty':
                        icon_path = f"../assets/icons/{effect}.png"
                        try:
                            tex = self.loader.loadTexture(icon_path)
                            icon_dict[face] = tex
                        except:
                            pass
            elif 'icons' in cube_data:
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
            if face_name in icon_dict:
                face.setTexture(icon_dict[face_name])
                face.setColor(1, 1, 1, 1)
                face.setR(rot_dict.get(face_name, 0))
            else:
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
        if (player == 'p1' and self.current_player != 1) or \
           (player == 'p2' and self.current_player != 2):
            return
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

        # After selection, update right panel display
        player_obj = self.player1 if player == 'p1' else self.player2
        selected_idx = self.selected_p1_cube if player == 'p1' else self.selected_p2_cube
        self.deploy_mode = False
        self.deploy_cube_index = None
        if selected_idx is not None:
            if selected_idx < len(player_obj.cubes):
                cube_logic = player_obj.cubes[selected_idx]
                if cube_logic.deployable:
                    self.info_label['text'] = "Press Deploy Cube to deploy!"
                self.display_unfolded_cube({'logic': cube_logic})
                # If add side menu is open, check for a face click within the silhouette
                if not self.add_side_menu.isHidden():
                    face = self._detect_left_panel_face_click(player, index)
                    if face:
                        self.on_face_card_click(face)
            else:
                # Open slot but no cube built yet — show empty cross template
                self.display_unfolded_cube({})
        else:
            # Slot was deselected
            self.clear_unfolded_cube()
            self.hide_add_side_menu()
        self._update_action_buttons()

    # ─── Roll Menu ───────────────────────────────────────────────────────────

    def setup_roll_menu(self):
        """Setup the roll direction menu (initially hidden)"""
        self.roll_menu = DirectFrame(
            frameColor=(0.1, 0.1, 0.12, 0.9),
            frameSize=(-0.44, 0.44, -0.06, 0.06),
            pos=(GAME_AREA_CENTER, 0, -0.85)
        )
        self.roll_menu.hide()

        btn_size = 0.045
        btn_frame = (-btn_size, btn_size, -btn_size, btn_size)
        spacing = 0.11

        self.selected_roll_direction = None
        self.ability_triggered = False

        self.btn_normal_color  = (0.25, 0.30, 0.35, 1)
        self.btn_pressed_color = (0.15, 0.18, 0.22, 1)

        roll_buttons = [
            ("<",  "left",    -3 * spacing),
            ("^",  "up",      -2 * spacing),
            ("v",  "down",    -1 * spacing),
            (">",  "right",    0 * spacing),
            ("A",  "ability",  1 * spacing),
            ("OK", "confirm",  2 * spacing),
            ("X",  "cancel",   3 * spacing),
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
        self.selected_roll_direction = None
        self.ability_triggered = False
        for btn in self.roll_buttons.values():
            btn['frameColor'] = self.btn_normal_color
        self.roll_menu.show()

    def hide_roll_menu(self):
        """Hide the roll direction menu"""
        self.roll_menu.hide()

    def on_roll_button_click(self, button_name):
        """Handle roll menu button clicks"""
        self._gui_button_clicked = True
        if button_name in ["left", "up", "down", "right"]:
            if self.selected_roll_direction == button_name:
                self.roll_buttons[button_name]['frameColor'] = self.btn_normal_color
                self.selected_roll_direction = None
                self.info_label['text'] = "Select roll direction"
            else:
                if self.selected_roll_direction:
                    self.roll_buttons[self.selected_roll_direction]['frameColor'] = self.btn_normal_color
                self.roll_buttons[button_name]['frameColor'] = self.btn_pressed_color
                self.selected_roll_direction = button_name
                self.info_label['text'] = f"Roll {button_name}"

        elif button_name == "ability":
            self.ability_triggered = not self.ability_triggered
            if self.ability_triggered:
                self.roll_buttons["ability"]['frameColor'] = self.btn_pressed_color
                self.info_label['text'] = "Ability will trigger"
            else:
                self.roll_buttons["ability"]['frameColor'] = self.btn_normal_color
                self.info_label['text'] = "Ability disabled"

        elif button_name == "confirm":
            if self.selected_roll_direction and self.selected_cube:
                direction = self.selected_roll_direction
                cube_data = next((c for c in self.cubes if c['node'] == self.selected_cube), None)
                if cube_data is None:
                    self.info_label['text'] = "No cube selected!"
                    return
                x, y = cube_data['board_pos']
                if self.is_roll_legal(x, y, direction):
                    self.board.roll_cube(x, y, direction, perform_action=self.ability_triggered)
                    dx, dy = dir_to_coords[direction]
                    new_x, new_y = x + dx, y + dy
                    cube_data['board_pos'] = (new_x, new_y)
                    self.rolling = True
                    self.hide_roll_menu()

                    def on_roll_done():
                        self.rolling = False
                        self.update_cube_face_textures(cube_data)
                        self.display_unfolded_cube(cube_data)
                        self.end_turn()

                    self.animate_roll(cube_data, direction, on_roll_done)
                else:
                    self.info_label['text'] = "Illegal move!"
            elif not self.selected_roll_direction:
                self.info_label['text'] = "Select a direction first!"
            else:
                self.info_label['text'] = "Select a cube first!"

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

    # ─── Add Side Menu ───────────────────────────────────────────────────────

    def setup_add_side_menu(self):
        """Setup the add side menu (initially hidden)"""
        self.effects = ["slide", "push", "fortify", "grapple", "detonate",
                        "start", "rotate", "strength", "build", "slash"]

        script_dir = os.path.dirname(os.path.abspath(__file__))
        icons_dir = os.path.join(script_dir, "..", "assets", "icons")

        # Four rows: two effect rows, one rotation/ok/cancel row, one face row
        self.add_side_menu = DirectFrame(
            frameColor=(0.1, 0.1, 0.12, 0.9),
            frameSize=(-0.30, 0.30, -0.235, 0.12),
            pos=(GAME_AREA_CENTER, 0, -0.65)
        )
        self.add_side_menu.hide()

        btn_size = 0.05
        btn_frame = (-btn_size, btn_size, -btn_size, btn_size)
        spacing = 0.11

        self.selected_effect = None
        self.selected_face = None

        self.effect_buttons = {}
        img_scale = btn_size * 0.9

        # Row 1: first 5 effects
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

        # Row 2: remaining 5 effects
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

        # Row 3: rotate CW, rotate CCW, OK, X
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

        ccw_btn = DirectButton(
            image=cw_icon_path,
            image_scale=(-img_scale, img_scale, img_scale),
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

        # Face selection is now done by clicking the unfolded cube in the right panel
        self.face_buttons = {}

    def show_add_side_menu(self):
        """Show the add side menu"""
        self.selected_effect = None
        self.selected_face = None
        self.selected_rotation_deg = 0
        self.build_display_rotations = []
        for name, btn in self.effect_buttons.items():
            if name not in ["confirm", "cancel"]:
                btn['frameColor'] = self.btn_normal_color
                btn.setColorScale(1, 1, 1, 1)
        self.add_side_menu.show()
        self.info_label['text'] = "Select an effect, then click a face"

    def hide_add_side_menu(self):
        """Hide the add side menu"""
        self.add_side_menu.hide()

    def on_effect_button_click(self, effect_name):
        """Handle effect/rotation button clicks in the add side menu"""
        self._gui_button_clicked = True

        if effect_name in self.effects:
            # Effect selection — toggle
            if self.selected_effect == effect_name:
                self.effect_buttons[effect_name]['frameColor'] = self.btn_normal_color
                self.effect_buttons[effect_name].setColorScale(1, 1, 1, 1)
                self.selected_effect = None
                self.info_label['text'] = "Select an effect"
            else:
                if self.selected_effect:
                    self.effect_buttons[self.selected_effect]['frameColor'] = self.btn_normal_color
                    self.effect_buttons[self.selected_effect].setColorScale(1, 1, 1, 1)
                self.effect_buttons[effect_name]['frameColor'] = self.btn_pressed_color
                # Tint the icon so the selected state is obviously visible
                self.effect_buttons[effect_name].setColorScale(1.6, 1.6, 0.5, 1)
                self.selected_effect = effect_name
                self.info_label['text'] = f"Effect: {effect_name} — click a face"
            self._update_build_preview()

        elif effect_name in ("rotate_cw", "rotate_ccw"):
            # Rotate the effect direction preview on the selected face
            delta = 90 if effect_name == "rotate_cw" else -90
            self.selected_rotation_deg = (self.selected_rotation_deg + delta) % 360
            arrows = {0: '↑', 90: '→', 180: '↓', 270: '←'}
            direction = arrows.get(self.selected_rotation_deg, '?')
            self.info_label['text'] = f"Effect direction: {direction}"
            self._update_build_preview()

        elif effect_name == "confirm":
            if not self.selected_effect:
                self.info_label['text'] = "Select an effect first!"
            elif not self.selected_face:
                self.info_label['text'] = "Click a face on the cube first!"
            else:
                logic_face = FACE_GUI_TO_LOGIC[self.selected_face]
                if self.selected_p1_cube is not None:
                    player = self.player1
                    cube_idx = self.selected_p1_cube
                    container = self.player1_cube_containers[self.selected_p1_cube]
                else:
                    player = self.player2
                    cube_idx = self.selected_p2_cube
                    container = self.player2_cube_containers[self.selected_p2_cube]
                sil_scale = ((LEFT_PANEL_RIGHT - LEFT_PANEL_LEFT) / 3) * 0.85 / (4 * 0.08)
                if cube_idx >= len(player.cubes):
                    self.info_label['text'] = "No cube to add a side to! Build one first."
                    return
                player.upgrade_cube(cube_idx, logic_face, self.selected_effect, self.selected_rotation_deg)
                cube_logic = player.cubes[cube_idx]
                self.build_display_rotations = []  # rotations are now permanent
                self.display_flattened_cube(container, {'logic': cube_logic}, scale=sil_scale)
                self.display_unfolded_cube({'logic': cube_logic})
                self.hide_add_side_menu()
                self.end_turn()

        elif effect_name == "cancel":
            self._undo_build_rotations()
            self.info_label['text'] = "Add side cancelled"
            self.hide_add_side_menu()

    # ─── Action Buttons ──────────────────────────────────────────────────────

    def on_build_cube(self):
        """Build a new cube under construction (costs a turn)"""
        self._gui_button_clicked = True
        player = self.player1 if self.current_player == 1 else self.player2
        open_slots = self.player1_open_slots if self.current_player == 1 else self.player2_open_slots

        if open_slots >= 3:
            self.info_label['text'] = "Max construction slots reached!"
            return

        player.add_new_cube()

        if self.current_player == 1:
            idx = self.player1_open_slots
            self.player1_open_slots += 1
            self.player1_cube_slots[idx]['frameColor'] = (0.08, 0.08, 0.1, 1.0)
            panel_width = LEFT_PANEL_RIGHT - LEFT_PANEL_LEFT
            slot_width = panel_width / 3
            sil_scale = slot_width * 0.85 / (4 * 0.08)
            self.display_flattened_cube(self.player1_cube_containers[idx], None, scale=sil_scale)
        else:
            idx = self.player2_open_slots
            self.player2_open_slots += 1
            self.player2_cube_slots[idx]['frameColor'] = (0.08, 0.08, 0.1, 1.0)
            panel_width = LEFT_PANEL_RIGHT - LEFT_PANEL_LEFT
            slot_width = panel_width / 3
            sil_scale = slot_width * 0.85 / (4 * 0.08)
            self.display_flattened_cube(self.player2_cube_containers[idx], None, scale=sil_scale)

        self.end_turn()

    def on_add_side(self):
        """Handle add side button"""
        self._gui_button_clicked = True
        if self.selected_p1_cube is not None or self.selected_p2_cube is not None:
            self.show_add_side_menu()
        else:
            self.info_label['text'] = "Select a cube under construction first!"

    def on_end_turn(self):
        """Handle end turn button"""
        self._gui_button_clicked = True
        self.end_turn()

    # ─── Camera Controls ─────────────────────────────────────────────────────

    def rotate_left(self):
        self.camera_angle_h -= 15
        self.update_camera()

    def rotate_right(self):
        self.camera_angle_h += 15
        self.update_camera()

    def rotate_up(self):
        self.camera_angle_p = min(89, self.camera_angle_p + 10)
        self.update_camera()

    def rotate_down(self):
        self.camera_angle_p = max(-89, self.camera_angle_p - 10)
        self.update_camera()

    def zoom_in(self):
        self.camera_distance = max(8, self.camera_distance - 1)
        self.update_camera()

    def zoom_out(self):
        self.camera_distance = min(35, self.camera_distance + 1)
        self.update_camera()

    def reset_camera(self):
        self.camera_distance = 18
        self.camera_angle_h = 45
        self.camera_angle_p = 35
        self.update_camera()

    def update_camera(self):
        """Update camera position based on spherical coordinates"""
        rad_h = math.radians(self.camera_angle_h)
        rad_p = math.radians(self.camera_angle_p)

        x = self.camera_distance * math.cos(rad_p) * math.sin(rad_h)
        y = self.camera_distance * math.cos(rad_p) * math.cos(rad_h)
        z = self.camera_distance * math.sin(rad_p)

        self.camera.setPos(x, y, z)
        self.camera.lookAt(0, 0, 0)

        lens = self.cam.node().getLens()
        lens.setFilmOffset(0, 0)


if __name__ == '__main__':
    game = CubeGameGUI()
    game.run()
