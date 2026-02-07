from direct.showbase.ShowBase import ShowBase
from panda3d.core import *
from direct.task import Task
from direct.actor.Actor import Actor
from direct.gui.OnscreenText import OnscreenText
import sys

class Interactive3DGame(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)
        
        # Disable default mouse camera control
        self.disableMouse()
        
        # Setup camera
        self.camera_distance = 15
        self.camera_angle_h = 45
        self.camera_angle_p = 20
        self.update_camera()
        
        # Track mouse state
        self.last_mouse_x = 0
        self.last_mouse_y = 0
        self.mouse_dragging = False
        
        # Selected object
        self.selected_object = None
        
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
        
        # UI text
        self.title = self.addTitle("3D Interactive Game Demo")
        self.instructions = self.addInstructions(0.9, "[Left Mouse] Click to select | [Right Mouse] Drag to rotate view | [Scroll] Zoom")
        self.info_text = self.addInstructions(0.85, "Click on an object to select it!")
        
    def setup_scene(self):
        """Create the game objects"""
        self.objects = []
        
        # Ground plane
        cm = CardMaker("ground")
        cm.setFrame(-10, 10, -10, 10)
        ground = self.render.attachNewNode(cm.generate())
        ground.setP(-90)
        ground.setColor(0.3, 0.5, 0.3, 1)
        ground.setPos(0, 0, -0.1)
        
        # Create some simple 3D shapes
        # Cube 1
        cube1 = self.loader.loadModel("models/box")
        cube1.setScale(1, 1, 1)
        cube1.setPos(-3, 0, 0.5)
        cube1.setColor(1, 0.3, 0.3, 1)  # Red
        cube1.reparentTo(self.render)
        cube1.setTag('name', 'Red Cube')
        self.add_collision(cube1, 'cube1')
        self.objects.append({'node': cube1, 'name': 'Red Cube', 'original_color': (1, 0.3, 0.3, 1)})
        
        # Cube 2
        cube2 = self.loader.loadModel("models/box")
        cube2.setScale(0.8, 0.8, 1.5)
        cube2.setPos(3, 0, 0.75)
        cube2.setColor(0.3, 0.3, 1, 1)  # Blue
        cube2.reparentTo(self.render)
        cube2.setTag('name', 'Blue Tower')
        self.add_collision(cube2, 'cube2')
        self.objects.append({'node': cube2, 'name': 'Blue Tower', 'original_color': (0.3, 0.3, 1, 1)})
        
        # Sphere
        sphere = self.loader.loadModel("models/misc/sphere")
        sphere.setScale(0.7)
        sphere.setPos(0, 3, 0.7)
        sphere.setColor(0.3, 1, 0.3, 1)  # Green
        sphere.reparentTo(self.render)
        sphere.setTag('name', 'Green Sphere')
        self.add_collision(sphere, 'sphere')
        self.objects.append({'node': sphere, 'name': 'Green Sphere', 'original_color': (0.3, 1, 0.3, 1)})
        
        # Smiley (as a special object)
        smiley = self.loader.loadModel("models/misc/smiley")
        smiley.setScale(0.6)
        smiley.setPos(0, -3, 0.6)
        smiley.reparentTo(self.render)
        smiley.setTag('name', 'Smiley')
        self.add_collision(smiley, 'smiley')
        self.objects.append({'node': smiley, 'name': 'Smiley', 'original_color': None})
        
        # Add rotation animation to objects
        self.taskMgr.add(self.rotate_objects, "rotateObjects")
        
    def add_collision(self, node, name):
        """Add collision detection to an object"""
        # Get bounds and create collision sphere
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
        alight.setColor((0.4, 0.4, 0.4, 1))
        alnp = self.render.attachNewNode(alight)
        self.render.setLight(alnp)
        
        # Directional light
        dlight = DirectionalLight('dlight')
        dlight.setColor((0.8, 0.8, 0.8, 1))
        dlnp = self.render.attachNewNode(dlight)
        dlnp.setHpr(45, -60, 0)
        self.render.setLight(dlnp)
        
    def setup_controls(self):
        """Setup keyboard and mouse controls"""
        # Mouse controls
        self.accept('mouse1', self.on_mouse_click)  # Left click
        self.accept('mouse3', self.start_drag)  # Right click press
        self.accept('mouse3-up', self.stop_drag)  # Right click release
        self.accept('wheel_up', self.zoom_in)
        self.accept('wheel_down', self.zoom_out)
        
        # Keyboard
        self.accept('escape', sys.exit)
        self.accept('r', self.reset_camera)
        
        # Mouse movement
        self.taskMgr.add(self.mouse_task, "mouseTask")
        
    def on_mouse_click(self):
        """Handle left mouse click for object selection"""
        if self.mouseWatcherNode.hasMouse():
            mpos = self.mouseWatcherNode.getMouse()
            
            # Cast ray from camera through mouse position
            self.pickerRay.setFromLens(self.camNode, mpos.getX(), mpos.getY())
            
            self.picker.traverse(self.render)
            if self.pq.getNumEntries() > 0:
                self.pq.sortEntries()
                picked_obj = self.pq.getEntry(0).getIntoNodePath()
                
                # Find the parent node (the actual object)
                picked_node = picked_obj.findNetTag('name')
                if not picked_node.isEmpty():
                    name = picked_node.getTag('name')
                    self.select_object(picked_node, name)
            else:
                self.deselect_object()
    
    def select_object(self, node, name):
        """Select an object"""
        # Deselect previous
        if self.selected_object:
            obj_data = next((o for o in self.objects if o['node'] == self.selected_object), None)
            if obj_data and obj_data['original_color']:
                self.selected_object.setColor(*obj_data['original_color'])
        
        # Select new
        self.selected_object = node
        node.setColor(1, 1, 0, 1)  # Yellow highlight
        self.info_text.setText(f"Selected: {name}")
        
    def deselect_object(self):
        """Deselect current object"""
        if self.selected_object:
            obj_data = next((o for o in self.objects if o['node'] == self.selected_object), None)
            if obj_data and obj_data['original_color']:
                self.selected_object.setColor(*obj_data['original_color'])
            self.selected_object = None
            self.info_text.setText("Click on an object to select it!")
    
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
        self.camera_distance = max(5, self.camera_distance - 1)
        self.update_camera()
    
    def zoom_out(self):
        """Zoom camera out"""
        self.camera_distance = min(30, self.camera_distance + 1)
        self.update_camera()
    
    def reset_camera(self):
        """Reset camera to default position"""
        self.camera_distance = 15
        self.camera_angle_h = 45
        self.camera_angle_p = -20
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
    
    def rotate_objects(self, task):
        """Slowly rotate some objects"""
        for i, obj_data in enumerate(self.objects[:3]):  # Only cubes and sphere
            obj_data['node'].setH(obj_data['node'].getH() + 0.3 * (i + 1))
        return Task.cont
    
    def addTitle(self, text):
        """Add title text"""
        return self.addInstructions(0.95, text)
    
    def addInstructions(self, pos, msg):
        """Add instruction text"""
        return OnscreenText(text=msg, style=1, fg=(1, 1, 1, 1),
                          parent=self.aspect2d, align=TextNode.ALeft,
                          pos=(-1.3, pos), scale=.05)

# Run the game
if __name__ == '__main__':
    game = Interactive3DGame()
    game.run()