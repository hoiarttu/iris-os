"""
apps/stocks_app.py

stonks app

pin_mode = 'pinned' — lives in world space like a real mirage.
"""

import os, time, threading, json
import urllib.request
import urllib.error
import pygame
from apps.base_app import BaseApp
from core.display import WIDTH, HEIGHT, BLACK, WHITE, ACCENT, SECONDARY

_MONO_BOLD = 'assets/fonts/Rajdhani-Bold.ttf'

# market reader
class StockReader(threading.Thread):
    # from yahoo api

    def __init__(self):
        super().__init__(daemon=True)
        self.symbols = {
            'NVDA': 'NVDA',
            'MSFT': 'MSFT',
            'AAPL': 'AAPL',
            'AMZN': 'AMZN',
            'GOOG': 'GOOG',
            'META': 'META',
            'TSLA': 'TSLA'
        }
        
        self.market_data = {ticker: [0.0, 0.0, 0.0] for ticker in self.symbols.keys()}
        self._lock = threading.Lock()
        self._stop = False

    def run(self):
        # disguise as a standard browser to bypass bot checks (they fr didnt let me in otherwise lmao)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        while not self._stop:
            for display_sym, raw_sym in self.symbols.items():
                if self._stop: break
                
                url = f"https://query2.finance.yahoo.com/v8/finance/chart/{raw_sym}?interval=1d&range=1d"
                
                try:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=5) as response:
                        raw_data = json.loads(response.read().decode('utf-8'))
                        res = raw_data.get('chart', {}).get('result', [])
                        
                        if res:
                            meta = res[0].get('meta', {})
                            price = meta.get('regularMarketPrice', 0.0)
                            prev_close = meta.get('chartPreviousClose', meta.get('previousClose', 0.0))
                            
                            if price > 0:
                                abs_chg = price - prev_close
                                pct_chg = (abs_chg / prev_close) * 100 if prev_close > 0 else 0.0
                                
                                with self._lock:
                                    self.market_data[display_sym] = [price, abs_chg, pct_chg]
                except Exception as e:
                    pass # fail quietly
            
            time.sleep(10.0) # avoid ddos

    def get(self):
        with self._lock:
            return {k: list(v) for k, v in self.market_data.items()}

    def stop(self):
        self._stop = True


# the app

class StockApp(BaseApp):
    name          = 'Stocks'
    description   = 'The better casino'
    pin_mode      = 'pinned'
    show_cursor   = True
    cap_hold_secs = 0.0

    # UI colors
    COL_UP   = ( 80, 255, 120)  # bean green
    COL_DOWN = (255,  80,  80)  # red alarm
    COL_DIM  = ( 60,  60,  70)

    def __init__(self):
        super().__init__()

        self._reader = StockReader()
        self._reader.start()

        # fonts pre-load
        self._f_big    = pygame.font.Font(_MONO_BOLD, 36)
        self._f_price  = pygame.font.Font(_MONO_BOLD, 24)
        self._f_med    = pygame.font.Font(_MONO_BOLD, 22)
        self._f_sm     = pygame.font.Font(_MONO_BOLD, 16) 
        self._f_widget = pygame.font.Font(_MONO_BOLD, 18)

        # icon/widget setup
        fn = pygame.font.Font(_MONO_BOLD, 22)
        fi = pygame.font.Font(_MONO_BOLD, 18)
        self._name_surf = fn.render('STOCKS', True, WHITE)
        self._icon_surf = fi.render('ST',     True, WHITE)

        self._market_data = {}

    def close(self):
        self._reader.stop()
        super().close()

# update:::

    def update(self, dt):
        if not self._reader.is_alive():
            print('[Stocks] StockReader died — restarting')
            self._reader = StockReader()
            self._reader.start()

    #helpers
    def _val_color(self, change):
        if change > 0: return self.COL_UP
        if change < 0: return self.COL_DOWN
        return ACCENT

    def _row(self, surface, x, y, ticker, price, abs_chg, pct_change):
        col = self._val_color(pct_change)
        
        # 1. ticker name
        lbl = self._f_med.render(ticker, True, WHITE)
        surface.blit(lbl, (x, y))
        
        # 2. current price 
        prc_str = f'${price:,.2f}'
        prc = self._f_price.render(prc_str, True, ACCENT)
        surface.blit(prc, (x + 80, y - 2))
        
        # 3. today's change
        sign = '+' if abs_chg >= 0 else ''
        chg_str = f'{sign}{abs_chg:.2f}  ({sign}{pct_change:.2f}%)'
        chg = self._f_sm.render(chg_str, True, col)
        
        # align
        surface.blit(chg, (x + 280 - chg.get_width(), y + 4))

    # renders

    def draw_fullscreen(self, surface):
        surface.fill(BLACK)
        W, H = surface.get_size()
        cx   = W // 2
        y    = 20

        self._market_data = self._reader.get()

        # title
        t = self._f_big.render('STOCKS', True, ACCENT)
        surface.blit(t, (cx - t.get_width() // 2, y))
        y += t.get_height() + 16

        # divider ---
        pygame.draw.line(surface, self.COL_DIM, (40, y), (W - 40, y), 1)
        y += 20

        # sort by %, h-> l
        sorted_market = sorted(
            self._market_data.items(),
            key=lambda item: item[1][2], 
            reverse=True
        )

        # rows
        margin = 60
        for ticker, data in sorted_market:
            price, abs_chg, pct_chg = data
            self._row(surface, margin, y, ticker, price, abs_chg, pct_chg)
            y += 40

        # bottom divider
        y += 10
        pygame.draw.line(surface, self.COL_DIM, (40, y), (W - 40, y), 1)

    def draw_icon(self, surface, center, radius):
        r = self._icon_surf.get_rect(center=center)
        surface.blit(self._icon_surf, r)

    def draw_widget(self, surface, rect):
        self._market_data = self._reader.get()
        
        nr = self._name_surf.get_rect(
            centerx=rect.centerx, top=rect.top + 6)
        surface.blit(self._name_surf, nr)
        y = nr.bottom + 8

        # show top 3 by %
        sorted_stocks = sorted(
            self._market_data.items(), 
            key=lambda item: item[1][2], 
            reverse=True
        )[:3]
        
        for ticker, data in sorted_stocks:
            price, abs_chg, pct_chg = data
            col  = self._val_color(pct_chg)
            
            sign = '+' if pct_chg >= 0 else ''
            text = f'{ticker} {sign}{pct_chg:.1f}%'
            
            surf = self._f_widget.render(text, True, col)
            sr   = surf.get_rect(centerx=rect.centerx, top=y)
            surface.blit(surf, sr)
            y += surf.get_height() + 4
