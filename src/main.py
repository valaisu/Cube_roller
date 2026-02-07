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



# Rules:
max_unfinished_cubes = 3
effects = ["slide", "push", "fortify", "grapple", "detonate", "start", "rotate", "power", "build", "slash"]
# other ideas: 
# alert: damage anyone that moves next to this
# glue: block in front / in any dir cannot move
# ice: block landing in front / in any dir will slide forward before activating its ability
# activate: Trigger the ability of the cube in front / in any dir
# boost: cube landing next to / adjacent to this takes another turn

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

    def roll_cube(self, x, y, direction, perform_action = True, action_dir = (0, 0)):
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
            # s=2 slide to action_dir if possible
            pass
        elif effect == "push":
            # might have to rethink this
            # s=1 push next to blocks away from this
            # s=2 push next to blocks to any dir, deal 1 damage to ones that are blocked by other obstacles
            pass
        elif effect == "fortify":
            # s=1 cannot be moved by other effects
            # s=2 cannot be moved or destroyed by other effects
            pass
        elif effect == "grapple":
            # s=1 move block from -dir next to this
            # s=2 move block from action_dir to next to this
            pass
        elif effect == "detonate":
            # s=1 destroy this, adjacent cubes, and adjacent factories (4 squares)
            # s=2 destroy this, adjacent cubes, and adjacent factories (8 squares)
            pass
        elif effect == "start":
            # s=1 the cube has to start this side down
            # s=2 the cube has to start this side down. Triggering this cubes abilities is optional (during your turn?)
            pass
        elif effect == "rotate":
            # s=1 rotate this clock wise / counter clockwise
            # s=2 rotate this and adjacent cubes clock wise / counter clockwise (this moves the cubes. If a cube is moved to illegal square, it is destroyed)
            pass
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
            pass

        

class Side:
    def __init__(self, effect=None, strength=1):
        self.effect = effect
        self.strength = strength

class Cube:
    def __init__(self, owner=None):
        self.owner = owner
        self.u = Side()
        self.b = Side()
        self.r = Side()
        self.l = Side()
        self.f = Side()
        self.d = Side()

    def roll(self, direction):
        if direction == 'up':
            self.u, self.f, self.d, self.b = self.f, self.d, self.b, self.u
        elif direction == 'down':
            self.u, self.b, self.d, self.f = self.b, self.d, self.f, self.u
        elif direction == 'left':
            self.u, self.l, self.d, self.r = self.r, self.u, self.l, self.d
        elif direction == 'right':
            self.u, self.r, self.d, self.l = self.l, self.u, self.r, self.d

    def rotate(self, axis):
        if axis == 'x':
            self.f, self.r, self.b, self.l = self.l, self.f, self.r, self.b
        elif axis == 'y':
            self.u, self.r, self.d, self.l = self.l, self.u, self.r, self.d
        elif axis == 'z':
            self.u, self.f, self.d, self.b = self.b, self.u, self.f, self.d

    def get_effect(self):
        return self.u.effect, self.u.strength

    def get_owner(self):
        return self.owner

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