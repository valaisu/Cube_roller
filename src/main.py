

# Ok. So. we need the visuals, and we need the logic.


# 
#   u
# l b r
#   d
#   f
# 
"""
EFFECTS:

 - Slide forward / sideways / any direction
 - Push: Slide adjacent friend / opponent one away straight / in any dir
 - Fortify: cannot be moved by other effects / or destroyed
 - Grapple: bring cube next to this cube from specific / any direction
 - Detonate: destroy any adjacent cubes (4 / 8 tiles) 
 - Start: start this facing down / any direction. If upgraded, you can choose to not trigger abilities
 - Rotate: roll or rotate in place / do both
 - Power: If this face is facing up, the cube is allowed to move even if blocked in some direction. The cube that is blocking
   this cube will slide to the movement of the direction. If there is no empty space,the power cube cannot move / the blocking 
   cube is destroyed
 - Build: Add a new effect or upgrade to an existing cube in docs / anywhere 
"""

dir_to_coords = {
    'up': (0, -1),
    'down': (0, 1),
    'left': (-1, 0),
    'right': (1, 0)
}

DIRS = [(0, 1), (1, 0), (0, -1), (-1, 0)]
DIAGONAL_DIRS = [(1, 1), (1, -1), (-1, -1), (-1, 1)]

# Rules:
max_unfinished_cubes = 3
effects = ["slide", "push", "fortify", "grapple", "detonate", "start", "rotate", "power", "build", "slash"]
# other ideas: 
# alert: damage anyone that moves next to this
# glue: block in front / in any dir cannot move
# ice: block landing in front / in any dir will slide forward before activating its ability
# activate: Trigger the ability of the cube in front / in any dir
# boost: cube landing next to / adjacent to this takes another turn

def sum_tuples(a, b):
    return tuple(x+y for x, y in zip(a, b))

class Board:
    def __init__(self, width = 5, height = 7, exclusions=[0, 1, 4]):
        self.width = width
        self.height = height
        
        self.grid = [[None for _ in range(width)] for _ in range(height)]
        first_row = [None for _ in range(width)]
        for ex in exclusions:
            first_row[ex] = 'X'
        last_row = first_row.copy()[::-1]
        self.grid[0] = first_row
        self.grid[-1] = last_row

    def print_board(self):
        for row in self.grid:
            print(' | '.join([' ' if cell is None else str(cell) for cell in row]))
            print('-' * (self.width * 4 - 3))

    def slide_cube(self, x, y, direction):
        # check that this action is legal beforehand
        diff = dir_to_coords.get(direction)
        if y + diff[1] < 0 or y + diff[1] >= self.height or x + diff[0] < 0 or x + diff[0] >= self.width:
            print("illegal move, roll out of bounds")
            return
        if self.grid[y + diff[1]][x + diff[0]] is not None:
            print("illegal move, slide")
            return
        
        self.grid[y + diff[1]][x + diff[0]] = self.grid[y][x]
        self.grid[y][x] = None

    def roll_cube(self, x, y, direction, perform_action = True, action_dir = (0, 0), rotate_dir = None):
        # check that this action is legal beforehand
        diff = dir_to_coords.get(direction)
        cube = self.grid[y][x]
        if y + diff[1] < 0 or y + diff[1] >= self.height or x + diff[0] < 0 or x + diff[0] >= self.width:
            print("illegal move, roll out of bounds")
            return
        if not cube is type(Cube):
            return
        if self.grid[y + diff[1]][x + diff[0]] is not None:
            if not cube.get_effect()[0] == "power":
                print("illegal move, roll")
                return
            # TODO: add power logic
            
        cube.roll(direction)
        self.grid[y + diff[1]][x + diff[0]] = cube
        self.grid[y][x] = None

        # Then, here all of the effects trigger, and we need to check if it was a legal move and what ever
        # Guess I could build the visuals first and then worry about whether this works
        effect, strength = cube.get_effect()
        if effect == "slide": 
            # s=1 slide to direction if possible
            if strength == 1:
                slide_dir = cube.get_effect_dir()
            # s=2 slide to action_dir if possible
            elif strength == 2:
                slide_dir = action_dir

            if perform_action:
                dest = sum_tuples((x, y), slide_dir)
                if dest[0] < 0 or dest[0] >= self.width or dest[1] < 0 or dest[1] >= self.height:
                    print("slide blocked by edge")
                    return
                if self.grid[dest[1]][dest[0]] is not None:
                    print("slide blocked by cube")
                    return
                self.grid[dest[1]][dest[0]] = cube
                self.grid[y][x] = None
            return

        elif effect == "push":
            # s=1 push next to blocks away from this
            # s=2 push next to blocks to any dir, deal 1 damage to ones that are blocked by other obstacles
            for dir in DIRS:
                adj = sum_tuples((x, y), dir)
                if adj[0] < 0 or adj[0] >= self.width or adj[1] < 0 or adj[1] >= self.height:
                    continue
                adj_cube = self.grid[adj[1]][adj[0]]
                if isinstance(adj_cube, Cube):
                    if adj_cube.get_effect()[0] == "fortify":
                        print("push blocked by fortify")
                        continue
                    dest = sum_tuples(adj, dir)
                    if dest[0] < 0 or dest[0] >= self.width or dest[1] < 0 or dest[1] >= self.height:
                        if strength == 1:
                            print("push blocked by edge")
                            continue
                        elif strength == 2:
                            adj_cube.take_damage()
                            continue
                    if self.grid[dest[1]][dest[0]] is None:
                        self.grid[dest[1]][dest[0]] = adj_cube
                        self.grid[adj[1]][adj[0]] = None
                    else:
                        if strength == 1:
                            print("push blocked by cube")
                            continue
                        elif strength == 2:
                            adj_cube.take_damage()
            return

        elif effect == "fortify":
            # s=1 cannot be moved by other effects
            # s=2 cannot be moved or destroyed by other effects
            pass
        elif effect == "grapple":
            # s=1 move block from -dir next to this
            # s=2 move block from action_dir to next to this
            if not perform_action:
                return
            
            if strength == 1:
                grapple_dir = cube.get_effect_dir()
            elif strength == 2:
                grapple_dir = action_dir
            
            next_square = sum_tuples((x, y), grapple_dir)
            grapple_square = sum_tuples((x, y), (grapple_dir))
            # Find cube (if exist in grapple dir)
            while True:
                if grapple_square[0] < 0 or grapple_square[0] >= self.width or grapple_square[1] < 0 or grapple_square[1] >= self.height:
                    print("grapple blocked by edge")
                    return
                if self.grid[grapple_square[1]][grapple_square[0]] is not None:
                    break
                grapple_square = sum_tuples(grapple_square, grapple_dir)
            # Move cube
            self.grid[next_square[1]][next_square[0]] = self.grid[grapple_square[1]][grapple_square[0]]
            self.grid[grapple_square[1]][grapple_square[0]] = None

        elif effect == "detonate":
            # s=1 destroy this, adjacent cubes, and adjacent factories (4 squares)
            # s=2 destroy this, adjacent cubes, and adjacent factories (8 squares)
            if not perform_action:
                return
            
            loop = DIRS
            if strength == 2:
                loop = DIRS + DIAGONAL_DIRS

            for dir in loop:
                adj = sum_tuples((x, y), dir)
                if adj[0] < 0 or adj[0] >= self.width or adj[1] < 0 or adj[1] >= self.height:
                    continue
                adj_cube = self.grid[adj[1]][adj[0]]
                if isinstance(adj_cube, Cube):
                    if adj_cube.get_effect()[0] == "fortify" and adj_cube.get_effect()[1] == 2:
                        print("detonate blocked by fortify")
                        continue
                    adj_cube.is_destroyed()

        elif effect == "start":
            # s=1 the cube has to start this side down
            # s=2 the cube has to start this side down. Triggering this cubes abilities is optional (during your turn?)
            pass

        elif effect == "rotate":
            # s=1 rotate this clock wise / counter clockwise
            # s=2 rotate this and adjacent cubes clock wise / counter clockwise (this moves the cubes. If a cube is moved to illegal square, it is destroyed)
            if not perform_action:
                return
            
            cube.rotate(rotate_dir)
            if strength == 2:
                # rotate adjacent cubes AROUND THIS CUBE in rotate_dir
                # if for any reason the square to which a cube is supposed to be rotated to is blocked, that cube is destroyed instead
                blocked_squares = [] # out of bounds or fortified cubes
                for dir in DIRS:
                    adj = sum_tuples((x, y), dir)
                    if adj[0] < 0 or adj[0] >= self.width or adj[1] < 0 or adj[1] >= self.height:
                        blocked_squares.append(adj)
                        continue
                    adj_cube = self.grid[adj[1]][adj[0]]
                    if isinstance(adj_cube, Cube):
                        if adj_cube.get_effect()[0] == "fortify" and adj_cube.get_effect()[1] == 2:
                            blocked_squares.append(adj)
                            continue
                # next, destroy cubes that are supposed to be rotated to blocked squares, and rotate the rest
                for i in range(4):
                    dest = sum_tuples((x, y), DIRS[i])
                    if rotate_dir == "cw":
                        source = sum_tuples((x, y), DIRS[(i-1)%4])
                    elif rotate_dir == "ccw":
                        source = sum_tuples((x, y), DIRS[(i+1)%4])
                    
                    if self.grid[source[1]][source[0]] is None:
                        continue
                    if dest in blocked_squares:
                        if self.grid[source[1]][source[0]].get_effect()[0] != "fortify":
                            self.grid[source[1]][source[0]].is_destroyed()
                
                # finally, move and the cubes, we know none will be destroyed in this step
                dests = [sum_tuples((x, y), dir) for dir in DIRS]
                if rotate_dir == "cw":
                    sources = [sum_tuples((x, y), DIRS[(i-1)%4]) for i in range(4)]
                elif rotate_dir == "ccw":
                    sources = [sum_tuples((x, y), DIRS[(i+1)%4]) for i in range(4)]
                
                # we need to copy the cubes in order to rotate them without overwriting cubes that need to be rotated
                cubes_to_rotate = [self.grid[source[1]][source[0]] for source in sources]
                for i in range(4):
                    if isinstance(cubes_to_rotate[i], Cube):
                        self.grid[dests[i][1]][dests[i][0]] = cubes_to_rotate[i]
                        self.grid[dests[i][1]][dests[i][0]].rotate(rotate_dir)
                        self.grid[sources[i][1]][sources[i][0]] = None

        elif effect == "power":
            # s=1 if this is facing up before moving, the cube is allowed to slide the blocking cube to direction before moving, unless that cube is blocked
            # s=2 if this is facing up before moving, the cube is allowed to slide the blocking cube to direction before moving. If the cube is blocked, it gets destroyed.            
            pass

        elif effect == "build":
            # s=1 the player can upgrade/add a side to a cube under construction
            # s=2 the player can upgrade/add a side to up to 2 distinct cubes under construction
            # s2 could also be "to a cube under construction or on the battlefield", though this might be too strong
            pass
        elif effect == "slash":
            # s=1 deal one damage to the cube / empty factory in direction
            # s=2 deal one damage to all adjacent cubes / empty factories
            if strength == 1:
                slash_dirs = [cube.get_effect_dir()]
            elif strength == 2:
                for dir in DIRS:
                    target = sum_tuples((x, y), dir)
                    if target[0] < 0 or target[0] >= self.width or target[1] < 0 or target[1] >= self.height:
                        continue
                    if self.grid[target[1]][target[0]] is not None:
                        self.grid[target[1]][target[0]].take_damage()


        

class Side:
    def __init__(self, effect=None, strength=1):
        self.effect = effect
        self.strength = strength

class Cube:
    # ok so I kinda think it would be good that these have a direction also. 
    # I guess the simplest way is to define their rotation in relation to 
    # 2D flattening. 
    #   u
    # l f r
    #   d
    #   b
    # I don't remember if this is the flattening that was used in the GUI side
    #  
    def __init__(self, x, y, board, owner=None):
        self.owner = owner
        self.u = Side()
        self.u_rot = 0 # in degs
        self.b = Side()
        self.b_rot = 0
        self.r = Side()
        self.r_rot = 0
        self.l = Side()
        self.l_rot = 0
        self.f = Side()
        self.f_rot = 0
        self.d = Side()
        self.d_rot = 0

        self.x = x
        self.y = y

        self.under_construction = True
        self.destroyed = False

        self.board = board

    # Ok then I need a mapping that outputs where each side is facing

    def roll(self, direction):
        if direction == (0, 1):#'up'
            self.u, self.f, self.d, self.b = self.f, self.d, self.b, self.u
            # does not edit rot's
        elif direction == (0, -1):#'down'
            self.u, self.b, self.d, self.f = self.b, self.d, self.f, self.u
            # does not edit rot's
        elif direction == (-1, 0):#'left'
            self.l, self.f, self.r, self.b = self.f, self.r, self.b, self.l
            self.l_rot, self.f_rot, self.r_rot, self.b_rot = \
                self.f_rot, self.r_rot, (self.b_rot+180)%360, (self.l_rot+180)%360
        elif direction == (1, 0):#'right'
            self.l, self.f, self.r, self.b = self.b, self.l, self.f, self.r
            self.l_rot, self.f_rot, self.r_rot, self.b_rot = \
                (self.b_rot+180)%360, self.l_rot, self.f_rot, (self.r_rot+180)%360

    def rotate(self, dir):
        if dir == "cw":
            self.u, self.l, self.d, self.r = self.l, self.d, self.r, self.u
            self.u_rot, self.l_rot, self.d_rot, self.r_rot = \
                (self.l_rot+90)%360, (self.d_rot+90)%360, (self.r_rot+90)%360, (self.u_rot+90)%360
        elif dir == "ccw":
            self.u, self.l, self.d, self.r = self.r, self.u, self.l, self.d
            self.u_rot, self.l_rot, self.d_rot, self.r_rot = \
                (self.r_rot-90)%360, (self.u_rot-90)%360, (self.l_rot-90)%360, (self.d_rot-90)%360
        else:
            print("sus rotation")

    def get_effect(self):
        return self.u.effect, self.u.strength

    def get_effect_dir(self):
        return DIRS[int(self.u_rot/90)]

    def get_owner(self):
        return self.owner

    def get_loc(self):
        return (self.x, self.y)

    def take_damage(self):
        if self.u.strength == 2:
            self.u.strength = 1
        elif self.u.strength == 1:
            self.u.effect = None
            self.u.strength = 0
        else:
             self.is_destroyed()

    def is_destroyed(self):
        if self.u.effect == "fortify" and self.u.strength == 2:
            print("fortify blocked destruction")
            return
        self.destroyed = True
    
    # TODO: consider adding a function for moving the cube. Would handle being blocked more cleanly


class Player:
    def __init__(self, name):
        self.name = name
        self.cubes = []

    def add_new_cube(self):
        cube = Cube()
        self.cubes.append(cube)


def main():
    p1 = Player("1")
    p2 = Player("2")
    board = Board()
    board.print_board()

if __name__ == "__main__":
    main()