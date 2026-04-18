"""
apps/testgame_app.py : Shoot moving targets ()
"""

import pygame, time
from apps.base_app import BaseApp
import random
from pygame.locals import *
from core.display          import screen, canvas, clock, CENTER, WIDTH, HEIGHT, FPS, BLACK, WHITE, ACCENT

_MONO      = 'assets/fonts/Rajdhani-Bold.ttf'
_MONO_BOLD = 'assets/fonts/Rajdhani-Bold.ttf'
_TARGET_PATH='assets/Target_PLACEHOLDER.png'
_POINTER_PATH='assets/LOGO.png'


# BGCOLOR = (0, 0, 0)
BGCOLOR = BLACK #See if this works or use line above
SCORECOLOR = (123,123,123) #Some sort of gray

#Size of the game area (Targets stay here)
GAMEAREA_WIDTH = 1280
GAMEAREA_HEIGHT = 720

# Maximum speed of target (per cardinal direction, so it can go at that speed both x direction and y direction, so really sqrt(2)*MAXSPEED)
MAXSPEED = 5

# Number of times target moves before changing direction 
MAXSTEPS = 10



class Target(pygame.sprite.Sprite): #Class for target entities. They need reference surface (refrect) to move on
      def __init__(self, refrect): 
        super().__init__() 
        
        #Save current location of reference surface
        self.refrect=refrect
        self.x_ref = self.refrect.x
        self.y_ref = self.refrect.y
        
        #Spawn target somewhere in reference surface
        self.image = pygame.transform.scale_by(pygame.image.load(_TARGET_PATH).convert_alpha(),0.1)
        self.rect = self.image.get_rect()
        self.rect.center = (random.randint(self.x_ref, self.x_ref + GAMEAREA_WIDTH), random.randint(self.y_ref, self.y_ref + GAMEAREA_HEIGHT))  
        
        
        #Set starting velocities
        self.x_vel = random.randint(-MAXSPEED, MAXSPEED)
        self.y_vel = random.randint(-MAXSPEED, MAXSPEED)
        self.steps_from_change = 0
 
      def move(self):
        
         # Calculates new location of the target (Movement of reference surface + target)
        new_x=  self.refrect.x - self.x_ref + self.x_vel
        new_y=  self.refrect.y - self.y_ref + self.y_vel
        
        # Saves the new location of reference surface
        self.x_ref=self.refrect.x
        self.y_ref=self.refrect.y
        
        # Moves the target (clamp keeps it within reference surface)
        self.rect.move_ip(new_x,new_y)
        self.rect.clamp_ip(self.refrect)
        
        # counts steps taken and changes velocity when MAXSTEPS is reached
        self.steps_from_change +=1
        if (self.steps_from_change > MAXSTEPS):
            self.steps_from_change = 0
            self.x_vel = random.randint(-MAXSPEED, MAXSPEED)
            self.y_vel = random.randint(-MAXSPEED, MAXSPEED)
            
            
            
class Pointer(pygame.sprite.Sprite): #Class for pointer. Stays stationary on screen perspective, but moves reference surface (refrect) to opposing direction
    def __init__(self, refrect):
        super().__init__() 
        
        #Sets pointer to middle of screen
        self.image = pygame.transform.scale_by(pygame.image.load(_POINTER_PATH).convert(),0.01)
        self.rect = self.image.get_rect()
        self.rect.center = (WIDTH/2, HEIGHT/2)
        
        #Saves the reference surface
        self.BGrect=refrect
        
    def move(self): #Moves reference surface, making it look like the pointer moves
        pressed_keys = pygame.key.get_pressed()
        if pressed_keys[K_UP]:
            # self.rect.move_ip(0, -5)
            # BGrect.move_ip(0, 5)
            self.BGrect.y -=10 #inverted
        if pressed_keys[K_DOWN]:
            # self.rect.move_ip(0,5)
            # BGrect.move_ip(0, -5)
            self.BGrect.y +=10 #Inverted
         
        if pressed_keys[K_LEFT]:
            # self.rect.move_ip(-5, 0)
            # BGrect.move_ip(5, 0)
            self.BGrect.x +=10

        if pressed_keys[K_RIGHT]:
            # self.rect.move_ip(5, 0)
            # BGrect.move_ip(-5, 0)
            self.BGrect.x -=10

class TestgameApp(BaseApp): #The main app
    name        = 'Testgame'
    description = 'Shoot Targets'
    imu_mode      = 'world'   # kernel sends raw imu + hand each frame via on_imu()
    show_cursor   = False     # pointer sprite IS the cursor in this app
    cap_hold_secs = 1.5       # must hold cap before alpha/beta register
    _UPDATE_INTERVAL = 1/FPS

    def __init__(self):
        super().__init__()
        
        self._timer = 0.0
        self.font=pygame.font.Font(_MONO_BOLD, 80) #For score
        fn = pygame.font.Font(_MONO_BOLD, 20)
        fi = pygame.font.Font(_MONO_BOLD, 16)

        self._name_surf = fn.render('Testgame', True, (255, 255, 255)) # Text on top of middle hexagon
        self._icon_surf = fi.render('TG',     True, (255, 255, 255)) # Text in app hexagon
        
        
        # The "wall" where the game is projected. Supposed to stay stationary in real world while targets move inside the wall and the pointer moves independently
        self.background = pygame.image.load("assets/Ele2_Proju_Testgrid.png").convert()
        self.BGrect = self.background.get_rect()
        self.BGrect.center = (WIDTH/2, HEIGHT/2)
        
        #Creates pointer and target and add them to groups
        self.P1 = Pointer(self.BGrect)
        self.T1 = Target(self.BGrect)

        self.targets = pygame.sprite.Group()
        self.targets.add(self.T1)
        self.all_sprites = pygame.sprite.Group()
        self.all_sprites.add(self.P1)
        self.all_sprites.add(self.T1)

        #Sets score, shoot time and flag
        self.SCORE = 0
        self.lastshoot=time.time()
        self.shoot=False
        
        # IMU/hand pointer position (screen coords), set by on_imu()
        self._ptr_x = float(WIDTH  // 2)
        self._ptr_y = float(HEIGHT // 2)
        
        
        


    def on_event(self, event): #Kernel forwards events here instead of event.get()
        if event.type == pygame.KEYDOWN:
            if event.key == K_x:
                self.shoot = True

    def on_imu(self, imu_state, hand=None): #Called each frame with imu + hand state
        if hand and hand.active:
            # Hand takes over pointer when detected
            self._ptr_x = hand.x * WIDTH
            self._ptr_y = hand.y * HEIGHT
            if getattr(hand, 'pinch', False):
                self.shoot = True
        else:
            # IMU moves the world rect, pointer stays centred
            self._ptr_x = WIDTH  / 2
            self._ptr_y = HEIGHT / 2
            self.BGrect.x = int(WIDTH  / 2 - GAMEAREA_WIDTH  / 2 - imu_state.yaw   * 28)
            self.BGrect.y = int(HEIGHT / 2 - GAMEAREA_HEIGHT / 2 + imu_state.pitch * 24)

    def on_gesture(self, gesture): #Named gestures from kernel gesture detector
        if gesture == 'pinch':
            self.shoot = True

    def update(self, dt: float):
        self._timer += dt
        if self._timer >= self._UPDATE_INTERVAL: #Waits unti it is time for next frame
            self._timer = 0.0
            #Events now forwarded by kernel via on_event() — no event.get() needed here
            
            #Move pointer sprite to IMU/hand position (set each frame by on_imu)
            self.P1.rect.center = (int(self._ptr_x), int(self._ptr_y))
            
            #Moves pointer and targets according to their logic
            for entity in self.all_sprites:
                entity.move()
                
            #Shoot flag set by on_event (K_x), on_imu (pinch), or on_gesture — rate limited here
            if pygame.key.get_pressed()[K_x] and time.time() - self.lastshoot > 1:
                self.shoot=True
                self.lastshoot=time.time()
            
            #Shoots. Makes a pew noise and checks if target and pointer overlaps. Kills target, increase score and spawns new target if so 
            if self.shoot:
                pygame.mixer.Sound('assets/pew.wav').play()
                self.shoot=False            
                hit=pygame.sprite.spritecollideany(self.P1, self.targets)
                if hit:
                      hit.kill()
                      self.SCORE +=1
                      T2 = Target(self.BGrect)      
                      self.targets.add(T2)
                      self.all_sprites.add(T2)


    def draw_icon(self, surface, center, radius): #Draws icon hexagon in main menu
        r = self._icon_surf.get_rect(center=center)
        surface.blit(self._icon_surf, r)

    def draw_widget(self, surface, rect): #Draws the middle hexagon in main menu. Image of target should be good enough for test purposes
        
        #Title
        nr = self._name_surf.get_rect(centerx=rect.centerx, top=rect.top + 6)
        surface.blit(self._name_surf, nr)
        y = nr.bottom + 8
        
        #Image
        widget_target_surf=pygame.transform.scale_by(pygame.image.load(_TARGET_PATH).convert_alpha(),0.1)
        widget_target_rect=widget_target_surf.get_rect(centerx=rect.centerx, top=y)
        surface.blit(widget_target_surf, widget_target_rect)
        

    def draw_fullscreen(self, surface): #Draws the game
        
        surface.fill(BGCOLOR)
        surface.blit(self.background, self.BGrect) #Background
        scores = self.font.render(str(self.SCORE), True, SCORECOLOR)
        surface.blit(scores, (10,10)) #Score
        
        #Entities
        for entity in self.all_sprites:
            surface.blit(entity.image, entity.rect)
        
