"""
apps/testgame_app.py : Shoot moving targets. 515 lines before cleanup, 425 after
"""

import pygame, time
from apps.base_app import BaseApp
import random
from pygame.locals import *
from core.display          import screen, canvas, clock, CENTER, WIDTH, HEIGHT, FPS, BLACK, WHITE, ACCENT
import ntplib #For online time

_MONO      = 'assets/fonts/Rajdhani-Bold.ttf'
_MONO_BOLD = 'assets/fonts/Rajdhani-Bold.ttf'
_TARGET_PATH_GREEN='assets/Target_Green.png'
_TARGET_PATH_RED='assets/Target_Red.png'
_POINTER_PATH='assets/LOGO.png'
_AMMO_PATH='assets/ammo.png'



crosshair_image=pygame.image.load('assets/iris-app-targetgame.png').convert_alpha()
crosshair_size = int(35 * 1.4) 
_icon_cache = pygame.transform.smoothscale(crosshair_image, (crosshair_size, crosshair_size))
_icon_cache_size = crosshair_size #draw_icon can update this as I want the pointer to be same size as the icon


Red_Target = pygame.transform.scale_by(pygame.image.load(_TARGET_PATH_RED).convert_alpha(),1)
Green_Target = pygame.transform.scale_by(pygame.image.load(_TARGET_PATH_GREEN).convert_alpha(),1)
pew=pygame.mixer.Sound('assets/pew.wav')
BGCOLOR = BLACK
SCORECOLOR = (123,123,123) #Some sort of gray, should be visible on most backgrounds

#Size of the game area (Targets stay here)
GAMEAREA_WIDTH = 1280
GAMEAREA_HEIGHT = 720

# Starting maximum speed of target (per cardinal direction, so it can go at that speed both x direction and y direction, so really sqrt(2)*MAXSPEED). Will increase by one every time a target is shot
MAXSPEED = 0

# Number of times target moves before changing direction 
MAXSTEPS = 10

#Number of ammo player has after hitting a target
MAXAMMO=4

class Hole(pygame.sprite.Sprite): #A hole to mark the spot shot. Fades away after a  short while. They need a reference surface (refrect) where they stay stationary
    def __init__(self, refrect): 
        super().__init__() 
        
        #Save current location of reference surface
        self.refrect=refrect
        self.x_ref = self.refrect.x
        self.y_ref = self.refrect.y
        
        #Let's draw a hole
        self.radius=5
        self.image=pygame.Surface((2*self.radius,2*self.radius)).convert_alpha()
        self.image.fill((50,50,50)) #Just a some color, to be used as a colorkey. Just don't have same color as for the hole itself on next line
        pygame.draw.circle(self.image, (0,0,0), (5, 5), self.radius)
        self.image.set_colorkey(((50,50,50)))
        self.rect = self.image.get_rect()
        self.rect.center = (WIDTH/2, HEIGHT/2) #The hole appears to center, where the pointer also is
        self.alpha_counter=600 #For fade timer. Bigger the number, the longer it takes before the hole starts to fade. 255 to start immediately and smaller if you want to start partially faded
        
    def move(self): #While the hole doesn't 'move', we need it to follow background
        # Calculates new location of the hole
       new_x=  self.refrect.x - self.x_ref
       new_y=  self.refrect.y - self.y_ref
       
       # Saves the new location of reference surface
       self.x_ref=self.refrect.x
       self.y_ref=self.refrect.y
       
       # Moves the hole 
       self.rect.move_ip(new_x,new_y)


class Target(pygame.sprite.Sprite): #Class for target entities. They need a reference surface (refrect) to move on
    
    def get_Time(self): #Returns 1 if receives online time, -1 if not. Just to have IoT requirement fullfilled. Not really used as stock app did IoT better.
        c = ntplib.NTPClient()
        try:
            response = c.request('europe.pool.ntp.org', version=3) #This address responds with current time as seconds from probably 00:00:00 1.1.1970 (float)
            return int(response.tx_time)%60 #Gives the current second
        except: # If request fails, returns -1 as a sign of connection issue
            return -1
        
    def spawn_Location(self, second): #Selects a spot from gamearea to spawn new target. Used to use current second as part of calculation to fullfill IoT requirement.

        return (random.randint(self.x_ref, self.x_ref + GAMEAREA_WIDTH), random.randint(self.y_ref, self.y_ref + GAMEAREA_HEIGHT))    

    
    def __init__(self, refrect): 
        super().__init__() 
        self.speed=MAXSPEED #Saves current MAXSPEED, so it doesn't change when other targets get hit
        self.radius=60
        self.alpha_counter=600 #For fade timer. Bigger the number, the longer it takes before the target starts to fade. 255 to start immediately and smaller if you want to start partially faded
        self.alive=1 #Stops target if turned to 0.
        #Save current location of reference surface
        self.refrect=refrect
        self.x_ref = self.refrect.x
        self.y_ref = self.refrect.y
        
        #Spawn target somewhere in reference surface
        self.Spawn_Second=self.get_Time()
        self.image = pygame.Surface.copy(Red_Target)
        self.image.set_colorkey(((0,0,0))) #Black in target image will be transparent
        self.rect = self.image.get_rect()
        self.rect.center = self.spawn_Location(self.Spawn_Second)
        
        
        #Set starting velocities
        self.x_vel = random.randint(-self.speed, self.speed)
        self.y_vel = random.randint(-self.speed, self.speed)
        self.steps_from_change = 0
 
    def move(self): #Moves target on reference surface
        # Calculates new location of the target (Movement of reference surface + target)
        new_x=  self.refrect.x - self.x_ref + self.x_vel*self.alive
        new_y=  self.refrect.y - self.y_ref + self.y_vel*self.alive
        
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
            self.x_vel = random.randint(-self.speed, self.speed)*self.alive
            self.y_vel = random.randint(-self.speed, self.speed)*self.alive
            
        
            
            
class Pointer(pygame.sprite.Sprite): #Class for pointer. Stays stationary on screen.
    def __init__(self, refrect):
        super().__init__() 
        self.alpha_counter=600 #This is asked from all sprites, so here needs to be something. Will be transparent if less than 255
        #Sets pointer to middle of screen
        self.image = _icon_cache
        self.rect = self.image.get_rect()
        self.rect.center = (WIDTH/2, HEIGHT/2)
        
        #Saves the reference surface. Was needed in earlier version
        self.BGrect=refrect
        
    def move(self): #Used to move background with keyboard. Not needed anymore
        pressed_keys = pygame.key.get_pressed()
        


class TestgameApp(BaseApp): #The main app
    name        = 'Testgame'
    description = 'Shoot Targets'
    imu_mode      = 'world'   # kernel sends raw imu + hand each frame via on_imu()
    show_cursor   = False     # pointer sprite IS the cursor in this app
    cap_hold_secs = 1.5       # must hold cap before alpha/beta register
    _UPDATE_INTERVAL = 1/FPS  # Time between frames
    
    pin_mode = 'world' #Let's app handle the response to user movement.
    
    def __init__(self):
        super().__init__()
        
        self.ammo=MAXAMMO
        self._timer = 0.0
        self.running=True
        self.font=pygame.font.Font(_MONO_BOLD, 80) #For score and Game Over screen
        self.fn = pygame.font.Font(_MONO_BOLD, 20) #For widget text and Game Over screen
        self.fi = pygame.font.Font(_MONO_BOLD, 16) #For icon text

        self._name_surf = self.fn.render('Testgame', True, (255, 255, 255)) # Text on top of middle hexagon
        self._icon_surf = self.fi.render('TG',     True, (255, 255, 255)) # Text in app hexagon
        
        
        # The "wall" where the game is projected. Supposed to stay stationary in real world while targets move inside the wall and the pointer moves independently
        self.background = pygame.image.load("assets/Ele2_Proju_Testgrid.png").convert()
        self.BGrect = self.background.get_rect()
        self.BGrect.center = (WIDTH/2, HEIGHT/2)
        
        #Creates pointer and targets and add them to groups
        self.P1 = Pointer(self.BGrect)
        self.T1 = Target(self.BGrect)
        self.T2 = Target(self.BGrect)

        self.targets = pygame.sprite.Group()
        self.targets.add(self.T1)
        self.targets.add(self.T2)
        self.all_sprites = pygame.sprite.Group()
        self.all_sprites.add(self.P1)
        self.all_sprites.add(self.T1)
        self.all_sprites.add(self.T2)
        
        self.holes = pygame.sprite.Group()
        #Sets score, shoot time and flag
        self.SCORE = 0
        self.lastshoot=time.time()
        self.shoot=False # No longer used
        
        self.hit_targets = pygame.sprite.Group() # To be rendered right after background
        self.faders = pygame.sprite.Group() # For holes and hit targets, to make them fade over time
        
        
        # IMU/hand pointer position (screen coords), set by on_imu()
        self._ptr_x = float(WIDTH  // 2)
        self._ptr_y = float(HEIGHT // 2)
        
        self.ammo_image = pygame.transform.scale_by(pygame.image.load(_AMMO_PATH).convert_alpha(),1)
        
        


    def on_event(self, event): #Functionality moved to on_imu
        if event.type == pygame.KEYDOWN:
                pass

    def on_imu(self, imu_state, hand=None): #Called each frame with imu + hand state
        if hand and hand.active:
            # Hand takes over pointer when detected
            self._ptr_x = hand.x * WIDTH
            self._ptr_y = hand.y * HEIGHT
            if getattr(hand, 'pinch', False):
                self.try_shoot()
        else:
            # IMU moves the world rect, pointer stays centred
            self._ptr_x = WIDTH  / 2
            self._ptr_y = HEIGHT / 2
            
            #Reformats given angle from [0,360] to [-180,180]. Otherwise game thinks that pointer is e.g. 359 degrees to right instead of 1 degree left, moving pointer far away from gamearea when looking left  
            temp_yaw=imu_state.yaw
            if temp_yaw>180:
                temp_yaw-=360
            # Moves background to cancel user movements
            self.BGrect.x = int(WIDTH  / 2 - GAMEAREA_WIDTH  / 2 - temp_yaw   * 28)
            self.BGrect.y = int(HEIGHT / 2 - GAMEAREA_HEIGHT / 2 + imu_state.pitch * 24)
            

    def on_gesture(self, gesture): #Named gestures from kernel gesture detector
        if gesture == 'pinch':
            self.try_shoot()

    def update(self, dt: float):
        self._timer += dt
        if self._timer >= self._UPDATE_INTERVAL: #Waits unti it is time for next frame
            self._timer = 0.0
            
            #Move pointer sprite to IMU/hand position (set each frame by on_imu)
            self.P1.rect.center = (int(self._ptr_x), int(self._ptr_y))
            
            #Moves pointer, holes and targets according to their logic
            for entity in self.all_sprites:
                entity.move()
                if entity.alpha_counter<0: #Removes sprites that have faded away
                    entity.kill()
            
            #Reduces alpha_counter and applies new alpha to sprites in faders-group
            for fader in self.faders:
                fader.alpha_counter-=10
                fader.image.set_alpha(fader.alpha_counter)
      

    def game_over(self): #Makes the Game Over screen
        self.running=False #Makes the Game Over screen appear
        self.GameOver_screen=pygame.Surface((400,200)).convert_alpha()
        GO_BG = pygame.Surface((400,200)).convert_alpha()
        GO_BG.fill(BGCOLOR)
        
        GO = self.font.render("Game Over!", True, SCORECOLOR)
        GO_rect=GO.get_rect()
        YS = self.fn.render(f"Your score: {self.SCORE}", True, SCORECOLOR)
        YS_rect=YS.get_rect()
        RT = self.fn.render("Shoot to retry", True, SCORECOLOR)
        RT_rect=RT.get_rect()
        
        # This was an attempt to make a button for restarting game. Doesn't work atm
        self.reset_button=pygame.sprite.Sprite()
        self.reset_button.image=pygame.Surface((RT_rect.w +20,RT_rect.h +20)).convert_alpha()
        self.reset_button.image.fill((20,60,10))
        self.reset_button.image.blit(RT,(10,10))
        self.reset_button.rect=self.reset_button.image.get_rect()
        self.reset_button.rect.center=(200-RT_rect.w/2,200-RT_rect.h-30)

        #Creates the game over screen
        self.GameOver_screen.blit(GO, (200-GO_rect.w/2,0))
        self.GameOver_screen.blit(YS, (200-YS_rect.w/2,GO_rect.h))
        self.GameOver_screen.blit(RT, (200-RT_rect.w/2,GO_rect.h + YS_rect.h*2))
        
        
    def retry(self): #Resets the game
        
        self.ammo=MAXAMMO
        self._timer = 0.0
        self.running=True
        global MAXSPEED
        MAXSPEED = 0

        
        #Creates pointer and target and add them to groups
        self.T1 = Target(self.BGrect)
        self.T2 = Target(self.BGrect)

        self.targets = pygame.sprite.Group()
        self.targets.add(self.T1)
        self.targets.add(self.T2)
        self.all_sprites = pygame.sprite.Group()
        self.all_sprites.add(self.P1)
        self.all_sprites.add(self.T1)
        self.all_sprites.add(self.T2)
        
        self.holes = pygame.sprite.Group()
        #Sets score, shoot time and flag
        self.SCORE = 0
        self.lastshoot=time.time()
        self.shoot=False
        
        self.hit_targets = pygame.sprite.Group()
        self.faders = pygame.sprite.Group()
        
        
        # IMU/hand pointer position (screen coords), set by on_imu()
        self._ptr_x = float(WIDTH  // 2)
        self._ptr_y = float(HEIGHT // 2)
        
        self.ammo_image = pygame.transform.scale_by(pygame.image.load(_AMMO_PATH).convert_alpha(),1)
        
    def try_shoot(self): #shoots if last time shot was over a second ago
        if self.running:
            if time.time() - self.lastshoot > 1:
                self.shoot=True # Not used anymore
                pew.play()
                self.lastshoot=time.time()
                #Creates a new hole and adds it to relevant groups
                self.H=Hole(self.BGrect)
                self.holes.add(self.H)
                self.faders.add(self.H)
                self.all_sprites.add(self.H)
                self.ammo-=1
                
                hit=pygame.sprite.spritecollideany(self.H, self.targets) #Checks if the hole rectangle hits any target rectangle
                
                if hit and pygame.sprite.collide_circle(hit, self.H): #Checks if the target was actually hit, instead of the corner of rectangle with no actual target. Keep 'hit' as first condition, as if it is 'None', we never process second condition where 'hit' as 'None' would cause an error
                      hit.alive=0 #Stops the target
                      hit.image=pygame.Surface.copy(Green_Target) #Changes to green target to indicate it was hit
                      hit.image.set_colorkey(((0,0,0))) #Black in target image will be transparent
                      #Moves hit target from targets group to hit_targets and faders groups
                      self.targets.remove(hit)
                      self.hit_targets.add(hit)
                      self.faders.add(hit)
                      self.SCORE +=1
                      global MAXSPEED
                      MAXSPEED +=1
                      #Spawns a new target
                      T2 = Target(self.BGrect)      
                      self.targets.add(T2)
                      self.all_sprites.add(T2)
                      self.ammo=MAXAMMO #Replenish ammo
                      
                if self.ammo<1:
                    self.game_over()
            
        else: #Resets game if shot on game over screen
            self.retry()



    def draw_icon(self, surface, center, radius): #Draws icon on hexagon menu. This will also be pointer, as I want them to be same size
        cache_key = int(radius * 1.4)
        if getattr(self, '_icon_cache_size', None) != cache_key:
            try:
                img = crosshair_image
                size = cache_key
                self._icon_cache = pygame.transform.smoothscale(img, (size, size))
                self._icon_cache_size = cache_key
            except Exception:
                self._icon_cache = getattr(self, '_icon_surf', None)
                self._icon_cache_size = cache_key
        if self._icon_cache:
            r = self._icon_cache.get_rect(center=center)
            surface.blit(self._icon_cache, r)

    def draw_widget(self, surface, rect): #Draws the middle hexagon in main menu. Image of target should be good enough for test purposes
        
        #Title
        nr = self._name_surf.get_rect(centerx=rect.centerx, top=rect.top + 6)
        surface.blit(self._name_surf, nr)
        y = nr.bottom + 8
        
        #Image
        widget_target_surf=pygame.transform.scale_by(pygame.image.load(_TARGET_PATH_GREEN).convert_alpha(),0.5)
        widget_target_rect=widget_target_surf.get_rect(centerx=rect.centerx, top=y)
        surface.blit(widget_target_surf, widget_target_rect)
        

    def draw_fullscreen(self, surface): #Draws the game
        #Order of rendering: Background -> Hit targets -> Holes -> Living targets -> Possible game over screen -> Score -> Ammo -> Pointer
    
        surface.fill(BGCOLOR)
        surface.blit(self.background, self.BGrect) #Background
        
        
        for target in self.hit_targets:
            surface.blit(target.image, target.rect)
        
        for dot in self.holes:
            surface.blit(dot.image, dot.rect)
        
        for target in self.targets:
            surface.blit(target.image, target.rect)
            
        if not self.running:
            surface.blit(self.GameOver_screen, (self.BGrect.center[0]-200,self.BGrect.center[1]-100))
            
            
        scores = self.font.render(str(self.SCORE), True, SCORECOLOR)
        surface.blit(scores, (WIDTH/2,30)) #Score, located on middle top
        
        for i in range(self.ammo):
            surface.blit(self.ammo_image, (WIDTH/2 +i*11,120)) #Located under score
        
        surface.blit(self.P1.image, self.P1.rect) #Draws pointer to top