"""
CAN alım katmanı (4. hafta): EMU ölçüm mesajlarının E2E izleyicisi ve ECU tarafı alım modeli.

  0x101 = V, I, T          0x102 = V_min, V_max (+ T_amb)          periyot 100 ms = Ts

CanMonitor: tek bir periyodik mesaj için CRC + 4 bitlik alive counter + zaman aşımı izleyicisi.
  CRC hatası            -> reddedilir (n_crc_err)
  sayaç farkı 0         -> donmuş sayaç / tekrar, reddedilir (n_cnt_err)
  sayaç farkı 2..3      -> arada kayıp çerçeve var ama kabul (n_lost += fark - 1)
  sayaç farkı > 3       -> dizi hatası, reddedilir; sayaç yeniden eşitlenir (n_cnt_err)
  zaman aşımı: son geçerli mesajdan >= 250 ms fault (kendiliğinden kalkar), >= 500 ms safe (kalıcı)
  birlikte (100 ms periyot, bilinçli seçim): 1-2 kayıp kabul; 3 kayıpta dönüş çerçevesi reddedilir ama
          SAFE yok (yaş 497 ms); 4+ kayıpta dönüş çerçevesi de reddedilir -> SAFE. Yani pratikte 4 ardışık
          kayıp SAFE-STOP'a götürür (AUTOSAR E2E "wrong sequence"; testler U3, U9, C2).
  açılış: henüz hiç geçerli mesaj yokken eşik 2000 ms (AUTOSAR "first timeout"); CRC'si bozuk
          çerçeveler bu süreyi uzatmaz.
CanRx: ECU'nun alım katmanı; kabul edilmeyen mesajda o mesajın ölçümleri son geçerli değerde tutulur
  (sıfır dereceli tutucu), CAN_ok = iki izleyiciden hiçbiri safe değil -> karar mekanizması SAFE-STOP.
  Arıza enjeksiyonu: mode 1 çerçeve kaybı, 2 CRC bozuk, 3 donmuş alive counter;
                     msg bit maskesi 1 = 0x101, 2 = 0x102; t başlangıç [s], dur süre [s].

Python referansı; karşılıkları birebir aynı mantık:
  STM32     bms_ecu/bms/common/bms_can.c  (can_monitor_init / _rx / _tick)
  Simulink  simulink/can_monitor_init.m, can_monitor_rx.m, can_monitor_tick.m, can_rx.m
Zaman tamsayı ms (kayan nokta birikimi yok). Sabitler: simulink/bms_param_struct.m (can_*), bms_can.h.
"""
import math

T_FAULT_MS = 250
T_SAFE_MS = 500
T_FIRST_MS = 2000
MAX_DELTA = 3
COUNTER_MOD = 16


class CanMonitor:
    def __init__(self, now_ms=0):
        self.last_ok_ms = now_ms
        self.last_counter = 0
        self.have_counter = False
        self.fault = False
        self.safe = False
        self.n_ok = self.n_crc_err = self.n_cnt_err = self.n_lost = 0

    def rx(self, now_ms, crc_ok, counter):
        """Alınan bir çerçeve; True ise veri kullanılabilir."""
        if not crc_ok:
            self.n_crc_err += 1
            return False
        if self.have_counter:
            delta = (counter - self.last_counter) % COUNTER_MOD
            self.last_counter = counter
            if delta == 0 or delta > MAX_DELTA:
                self.n_cnt_err += 1
                return False
            self.n_lost += delta - 1
        else:
            self.have_counter = True
            self.last_counter = counter
        self.n_ok += 1
        self.last_ok_ms = now_ms
        return True

    def tick(self, now_ms):
        age = now_ms - self.last_ok_ms
        if not self.have_counter:
            if age >= T_FIRST_MS:
                self.fault = self.safe = True
            return
        self.fault = age >= T_FAULT_MS
        if age >= T_SAFE_MS:
            self.safe = True


class CanRx:
    """ECU alım katmanı; Simulink can_rx.m ile aynı (her adımda iki mesaj da gönderilir)."""

    def __init__(self, ts=0.1, mode=0, msg=3, t=600.0, dur=math.inf):
        self.ts, self.mode, self.msg, self.t, self.dur = ts, mode, msg, t, dur
        self.mon = (CanMonitor(0), CanMonitor(0))
        self.k = 0
        self.hold = None

    def step(self, meas1, meas2):
        """meas1 = (V, I, T), meas2 = (V_min, V_max) -> (tutulan meas1, tutulan meas2, CAN_ok, fault maskesi)"""
        if self.hold is None:
            self.hold = [tuple(meas1), tuple(meas2)]
        now_ms = round(self.k * self.ts * 1000)
        t0_ms = round(self.t * 1000)
        active = self.mode > 0 and t0_ms <= now_ms < t0_ms + self.dur * 1000
        cnt = self.k % COUNTER_MOD
        cnt_frozen = round(self.t / self.ts) % COUNTER_MOD
        for j, meas in enumerate((meas1, meas2)):
            hit = active and bool(self.msg & (1 << j))
            if hit and self.mode == 1:
                continue                                    # çerçeve hatta yok
            c = cnt_frozen if hit and self.mode == 3 else cnt
            if self.mon[j].rx(now_ms, not (hit and self.mode == 2), c):
                self.hold[j] = tuple(meas)
        for m in self.mon:
            m.tick(now_ms)
        self.k += 1
        can_ok = 0 if (self.mon[0].safe or self.mon[1].safe) else 1
        fault = int(self.mon[0].fault) + 2 * int(self.mon[1].fault)
        return self.hold[0], self.hold[1], can_ok, fault
