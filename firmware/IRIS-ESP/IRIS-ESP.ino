#include <Wire.h>
#include <Adafruit_NeoPixel.h>
#include <IRremote.hpp>
#include <esp_task_wdt.h>

// ── Pin definitions ───────────────────────────────────────────────────────────
#define CAP_ALPHA   5
#define CAP_BETA    4
#define RGB_PIN     2
#define IR_RX_PIN   9
#define FET_PIN     10
#define IR_TX_PIN   21
#define I2C_SDA     6
#define I2C_SCL     7
#define I2C_ADDR    0x42

// ── Timing ────────────────────────────────────────────────────────────────────
#define DEBOUNCE_MS          35
#define HOLD_STEP_MS         10
#define CONNECTION_TIMEOUT_MS 10000 // Increased to 10s to survive Pi "Spawn" lag
#define WDT_TIMEOUT_S        5      // 5s Watchdog
#define FADE                 0.12f

Adafruit_NeoPixel rgb(1, RGB_PIN, NEO_RGB + NEO_KHZ800);

// ── Registers ─────────────────────────────────────────────────────────────────
volatile uint8_t  reg_r = 80, reg_g = 220, reg_b = 255, reg_mode = 1;
volatile uint8_t  reg_fet = 0, reg_ir_tx = 0;
volatile uint32_t last_i2c_ms = 0;
volatile uint8_t  reg_status = 0, reg_events = 0, reg_ir_rx = 0;
volatile uint8_t  reg_alpha_hold = 0, reg_beta_hold = 0;
volatile uint8_t  request_reg = 0x00;

float cur_r = 0, cur_g = 0, cur_b = 0;
float tgt_r = 0, tgt_g = 0, tgt_b = 0;
bool  was_connected = false;

// ── Debounce ──────────────────────────────────────────────────────────────────
struct Input {
    uint8_t pin;
    bool raw_last = false, stable = false, stable_prev = false;
    uint32_t last_change = 0, hold_start = 0;
    uint16_t hold_ms = 0;
};
Input alpha_btn { CAP_ALPHA };
Input beta_btn  { CAP_BETA  };

void updateInput(Input &in, uint32_t now) {
    bool raw = digitalRead(in.pin);
    if (raw != in.raw_last) { in.raw_last = raw; in.last_change = now; }
    if ((now - in.last_change) >= DEBOUNCE_MS) in.stable = raw;
    if (in.stable != in.stable_prev) {
        if (in.stable) in.hold_start = now;
        else in.hold_ms = 0;
        in.stable_prev = in.stable;
    }
    in.hold_ms = in.stable ? (uint16_t)(now - in.hold_start) : 0;
}

// ── I2C handlers ─────────────────────────────────────────────────────────────
void onReceive(int len) {
    if (!Wire.available()) return;
    last_i2c_ms = millis();
    
    uint8_t first_byte = Wire.read();
    // Register Guard: The only software fix we actually need
    request_reg = (first_byte > 0x0F) ? 0x00 : first_byte;

    while (Wire.available()) {
        uint8_t val = Wire.read();
        switch (request_reg) {
            case 0x01: reg_r = val; break;
            case 0x02: reg_g = val; break;
            case 0x03: reg_b = val; break;
            case 0x04: reg_mode = val; break;
            case 0x05: reg_fet = val; break;
            case 0x06: reg_ir_tx = val; break;
        }
        request_reg++;
    }
}

void onRequest() {
    switch (request_reg) {
        case 0x00: Wire.write(reg_status); break;
        case 0x07: Wire.write(reg_ir_rx); break;
        case 0x09: Wire.write(reg_events); reg_events = 0; break;
        default:   Wire.write(0x00); break;
    }
}

// ── Setup ─────────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);

    // Watchdog: If the I2C hardware truly hangs the CPU, we reboot.
    // Watchdog: New v3.x syntax using the config struct
    esp_task_wdt_config_t twdt_config = {
        .timeout_ms = WDT_TIMEOUT_S * 1000,
        .idle_core_mask = (1 << portNUM_PROCESSORS) - 1,
        .trigger_panic = true,
    };
    esp_task_wdt_init(&twdt_config);
    esp_task_wdt_add(NULL);

    pinMode(CAP_ALPHA, INPUT_PULLDOWN);
    pinMode(CAP_BETA,  INPUT_PULLDOWN);
    pinMode(FET_PIN,   OUTPUT);
    analogWrite(FET_PIN, 0);

    Wire.setPins(I2C_SDA, I2C_SCL);
    // Setting 400kHz filter makes the ESP more tolerant of Pi speed jitter
    Wire.begin(I2C_ADDR, I2C_SDA, I2C_SCL, 400000); 
    Wire.onReceive(onReceive);
    Wire.onRequest(onRequest);

    rgb.begin();
    rgb.setBrightness(200); 
    rgb.show();

    IrReceiver.begin(IR_RX_PIN, DISABLE_LED_FEEDBACK);
    IrSender.begin(IR_TX_PIN);
    last_i2c_ms = millis();
}

// ── Loop ──────────────────────────────────────────────────────────────────────
void loop() {
    esp_task_wdt_reset(); // Feed the dog
    uint32_t now = millis();

    bool connected = (now - last_i2c_ms) < CONNECTION_TIMEOUT_MS;
    if (connected != was_connected) {
        Serial.println(connected ? "[IRIS-ESP] Pi connected" : "[IRIS-ESP] Pi lost");
        was_connected = connected;
    }

    // ── Inputs ────────────────────────────────────────────────────────────────
    bool alpha_prev = alpha_btn.stable, beta_prev = beta_btn.stable;
    updateInput(alpha_btn, now);
    updateInput(beta_btn,  now);

    uint8_t new_status = 0, new_events = 0;
    if (alpha_btn.stable) new_status |= 0x01;
    if (beta_btn.stable)  new_status |= 0x02;

    if (alpha_btn.stable && !alpha_prev) new_events |= 0x01;
    if (beta_btn.stable  && !beta_prev)  new_events |= 0x04;

    reg_status     = new_status;
    reg_events    |= new_events;
    reg_alpha_hold = (uint8_t)min((int)(alpha_btn.hold_ms / HOLD_STEP_MS), 255);
    reg_beta_hold  = (uint8_t)min((int)(beta_btn.hold_ms  / HOLD_STEP_MS), 255);

    // ── IR & FET ──────────────────────────────────────────────────────────────
    if (IrReceiver.decode()) { reg_ir_rx = IrReceiver.decodedIRData.command; IrReceiver.resume(); }
    if (reg_ir_tx != 0) { IrSender.sendNEC(0x00, reg_ir_tx, 0); reg_ir_tx = 0; }
    analogWrite(FET_PIN, reg_fet);

    // ── LED target ────────────────────────────────────────────────────────────
    if (!connected) {
        float b = (sinf((now / 1000.0f) * 1.2f) + 1.0f) / 2.0f;
        b = b * b * (3.0f - 2.0f * b);
        tgt_r = 255 * b; tgt_g = 80 * b; tgt_b = 0;
    } else {
        switch (reg_mode) {
            case 0: tgt_r = reg_r; tgt_g = reg_g; tgt_b = reg_b; break;
            case 1: { 
                float b = (sinf(now * 0.002f) + 1.0f) / 2.0f;
                b = b * b * (3.0f - 2.0f * b);
                tgt_r = reg_r * b; tgt_g = reg_g * b; tgt_b = reg_b * b;
                break;
            }
            case 2: { 
                bool on = ((now / 500) % 2) != 0;
                tgt_r = on ? reg_r : 0; tgt_g = on ? reg_g : 0; tgt_b = on ? reg_b : 0;
                break;
            }
            case 3: tgt_r = tgt_g = tgt_b = 0; break;
        }
    }

    cur_r += (tgt_r - cur_r) * FADE;
    cur_g += (tgt_g - cur_g) * FADE;
    cur_b += (tgt_b - cur_b) * FADE;

    static uint8_t lr, lg, lb;
    uint8_t or8 = (uint8_t)cur_r, og8 = (uint8_t)cur_g, ob8 = (uint8_t)cur_b;
    if (or8 != lr || og8 != lg || ob8 != lb) {
        rgb.setPixelColor(0, rgb.Color(or8, og8, ob8));
        rgb.show();
        lr = or8; lg = og8; lb = ob8;
    }
    delay(5);
}