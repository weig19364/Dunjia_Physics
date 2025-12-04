import http.server
import socketserver
import json
import datetime
import math
import sys
import os
import urllib.parse
import traceback

# ==========================================
# 0. 全局配置 (Global Config)
# ==========================================
PORT = 8000

PHYSICAL_STARS = {
    1: {"name": "天蓬", "astro": "Dubhe (Alpha Ursae Majoris)"},
    2: {"name": "天芮", "astro": "Merak (Beta Ursae Majoris)"},
    3: {"name": "天冲", "astro": "Phecda (Gamma Ursae Majoris)"},
    4: {"name": "天辅", "astro": "Megrez (Delta Ursae Majoris)"},
    5: {"name": "天禽", "astro": "Alioth (Epsilon Ursae Majoris)"},
    6: {"name": "天心", "astro": "Mizar (Zeta Ursae Majoris)"},
    7: {"name": "天柱", "astro": "Alkaid (Eta Ursae Majoris)"},
    8: {"name": "天任", "astro": "Alcor (80 Ursae Majoris)"},
    9: {"name": "天英", "astro": "Mizar B (Binary System)"}
}
DOORS_FEI = ['休门', '死门', '伤门', '杜门', '开门', '惊门', '生门', '景门']
GODS_YANG = ["值符", "螣蛇", "太阴", "六合", "勾陈", "太常", "朱雀", "九地", "九天"]
GODS_YIN  = ["值符", "螣蛇", "太阴", "六合", "白虎", "太常", "玄武", "九地", "九天"]
GAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

# ==========================================
# 1. 茅山历法核心 (Lunar Core)
# ==========================================
class LunarCore:
    def __init__(self):
        self.JU_MAP_YANG = {
            '冬至': [1, 7, 4], '小寒': [2, 8, 5], '大寒': [3, 9, 6],
            '立春': [8, 5, 2], '雨水': [9, 6, 3], '惊蛰': [1, 7, 4],
            '春分': [3, 9, 6], '清明': [4, 1, 7], '谷雨': [5, 2, 8],
            '立夏': [4, 1, 7], '小满': [5, 2, 8], '芒种': [6, 3, 9]
        }
        self.JU_MAP_YIN = {
            '夏至': [9, 3, 6], '小暑': [8, 2, 5], '大暑': [7, 1, 4],
            '立秋': [2, 5, 8], '处暑': [1, 4, 7], '白露': [9, 3, 6],
            '秋分': [7, 1, 4], '寒露': [6, 9, 3], '霜降': [5, 8, 2],
            '立冬': [6, 9, 3], '小雪': [5, 8, 2], '大雪': [4, 7, 1]
        }
        self.TERM_NAMES = [
            '冬至', '小寒', '大寒', '立春', '雨水', '惊蛰', '春分', '清明', '谷雨', '立夏', '小满', '芒种',
            '夏至', '小暑', '大暑', '立秋', '处暑', '白露', '秋分', '寒露', '霜降', '立冬', '小雪', '大雪'
        ]

    def get_gan_zhi(self, dt):
        base = datetime.datetime(2000, 1, 1)
        delta = (dt - base).days
        day_idx = (delta + 54) % 60
        
        d_gan_idx = day_idx % 10
        h_zhi_idx = int((dt.hour + 1) // 2) % 12
        h_gan_idx = ((d_gan_idx % 5) * 2 + h_zhi_idx) % 10
        y_idx = (dt.year - 1984) % 60
        
        return {
            "day_str": f"{GAN[day_idx%10]}{ZHI[day_idx%12]}",
            "hour_str": f"{GAN[h_gan_idx]}{ZHI[h_zhi_idx]}",
            "d_idx": day_idx,
            "h_gan": GAN[h_gan_idx],
            "h_zhi": ZHI[h_zhi_idx],
            "y_str": f"{GAN[y_idx%10]}{ZHI[y_idx%12]}"
        }

    def get_maoshan_ju(self, solar_lon, day_idx):
        lon = solar_lon % 360
        offset = (lon - 270) % 360
        term_idx = int(offset // 15)
        term_name = self.TERM_NAMES[term_idx]
        
        futou_idx = day_idx - (day_idx % 5)
        futou_zhi = futou_idx % 12
        
        yuan_idx = 2
        yuan_name = "下元"
        if futou_zhi in [0, 6, 3, 9]: yuan_idx=0; yuan_name="上元"
        elif futou_zhi in [2, 8, 5, 11]: yuan_idx=1; yuan_name="中元"
        
        is_yang = True if 0 <= term_idx <= 11 else False
        table = self.JU_MAP_YANG if is_yang else self.JU_MAP_YIN
        ju = table.get(term_name, [1,1,1])[yuan_idx]
        
        return {"ju": ju, "is_yang": is_yang, "term": term_name, "yuan": yuan_name, "desc": f"{term_name}{yuan_name}"}

# ==========================================
# 2. V12 物理引擎 (Physics Engine)
# ==========================================
class V12Engine:
    def __init__(self, lon):
        self.lon = lon
        self.stems = ['戊', '己', '庚', '辛', '壬', '癸', '丁', '丙', '乙']

    def get_true_solar(self, dt):
        doy = dt.timetuple().tm_yday
        b = (2 * math.pi / 365.24) * (doy - 81)
        eot = 9.87 * math.sin(2*b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
        offset = (self.lon - 120.0) * 4
        # 修复点：添加 datetime. 前缀
        return dt + datetime.timedelta(minutes=eot+offset), eot

    def get_astronomy(self, tst):
        doy = tst.timetuple().tm_yday
        solar_lon = ((doy - 80) * 0.9856 + 360) % 360 
        angle = (solar_lon + 90) % 360
        m_idx = int(((angle+7.5)%360)//30)
        month_build = ZHI[m_idx]
        jupiter = (105 + (tst.year - 2025)*30) % 360
        t_angle = (360 - jupiter) % 360
        y_idx = int((t_angle+15)//30)%12
        tai_sui = ZHI[y_idx]
        j_off = int(solar_lon/30)
        jiangs = ["戌", "酉", "申", "未", "午", "巳", "辰", "卯", "寅", "丑", "子", "亥"]
        yue_jiang = jiangs[j_off]
        return solar_lon, jupiter, month_build, angle, tai_sui, yue_jiang

    def get_di_pan(self, ju, is_yang):
        direction = 1 if is_yang else -1
        dp = {}
        for p in range(1, 10):
            idx = (((direction * (p - ju)) % 9) + 9) % 9
            dp[p] = self.stems[idx]
        return dp

    def deduce(self, ju, is_yang, h_gan, h_zhi):
        dp = self.get_di_pan(ju, is_yang)
        g_i = GAN.index(h_gan)
        z_i = ZHI.index(h_zhi)
        head_zhi_idx = (z_i - g_i + 12) % 12
        hidden_map = {0:'戊', 10:'己', 8:'庚', 6:'辛', 4:'壬', 2:'癸'}
        xun_stem = hidden_map.get(head_zhi_idx, '戊')
        src = 1
        for p, s in dp.items():
            if s == xun_stem: src = p
        target_s = h_gan if h_gan != '甲' else xun_stem
        dst_star = src
        for p, s in dp.items():
            if s == target_s: dst_star = p
        step = (z_i - head_zhi_idx + 12) % 12
        d = 1 if is_yang else -1
        curr = src
        for _ in range(step):
            curr = (curr + d - 1) % 9 + 1
            if curr == 5: curr = (curr + d - 1) % 9 + 1
        
        stars = {1:"天蓬", 2:"天芮", 3:"天冲", 4:"天辅", 5:"天禽", 6:"天心", 7:"天柱", 8:"天任", 9:"天英"}
        doors = {1:"休门", 2:"死门", 3:"伤门", 4:"杜门", 5:"中门", 6:"开门", 7:"惊门", 8:"生门", 9:"景门"}
        
        z_door = doors.get(src, "休门")
        if src == 5: z_door = "死门" 
        
        return {"zhifu": stars.get(src, "天蓬"), "zhishi": z_door, "star_pos": dst_star, "door_pos": curr}

# ==========================================
# 3. 飞盘算法
# ==========================================
def distribute(leader, target, direction, queue, skip5):
    try: idx = queue.index(leader)
    except: idx = 0
    path = []
    curr = target
    cnt = 8 if skip5 else 9
    for _ in range(cnt):
        path.append(curr)
        nxt = (curr + direction - 1) % 9 + 1
        if skip5 and nxt == 5: nxt = (nxt + direction - 1) % 9 + 1
        curr = nxt
    res = {}
    for i, pos in enumerate(path):
        val = queue[(idx + i) % len(queue)]
        res[pos] = val
    return res

# ==========================================
# 4. HTTP 服务器
# ==========================================
class V13Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Cache-Control', 'no-store')
        return super().end_headers()
        
    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        if not self.path.startswith('/api/state'):
            return super().do_GET()
            
        try:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            t_str = qs.get('time', [None])[0]
            try: now = datetime.datetime.strptime(t_str, "%Y-%m-%dT%H:%M") if t_str else datetime.datetime.now()
            except: now = datetime.datetime.now()
            try: lon = float(qs.get('lon', [120.0])[0]); lat = float(qs.get('lat', [30.0])[0])
            except: lon, lat = 120.0, 30.0
            is_south = lat < 0
            
            lunar = LunarCore()
            engine = V12Engine(lon)
            tst, eot = engine.get_true_solar(now)
            slon, jlon, m_build, d_ang, y_tai, y_jiang = engine.get_astronomy(tst)
            gz = lunar.get_gan_zhi(tst)
            dunjia = lunar.get_maoshan_ju(slon, gz['d_idx'])
            
            real_yang = dunjia['is_yang']
            if is_south: 
                real_yang = not real_yang
                dunjia['desc'] += " (南)"
                
            info = engine.deduce(dunjia['ju'], real_yang, gz['h_gan'], gz['h_zhi'])
            d = 1 if real_yang else -1
            sq = [PHYSICAL_STARS[i]["name"] for i in range(1, 10)]
            gq = GODS_YANG if real_yang else GODS_YIN
            
            star_map = distribute(info['zhifu'], info['star_pos'], d, sq, False)
            god_map = distribute("值符", info['star_pos'], d, gq, False)
            door_map = distribute(info['zhishi'], info['door_pos'], d, DOORS_FEI, True)
            dp = engine.get_di_pan(dunjia['ju'], real_yang)
            
            base_s = {1:"天蓬", 2:"天芮", 3:"天冲", 4:"天辅", 5:"天禽", 6:"天心", 7:"天柱", 8:"天任", 9:"天英"}
            s2h = {v:k for k,v in base_s.items()}
            tp = {}
            for pos, star in star_map.items():
                if not star: continue
                home = s2h.get(star)
                if home: tp[pos] = dp.get(home, "")

            g_i = GAN.index(gz['day_str'][0])
            z_i = ZHI.index(gz['day_str'][1])
            k_i = (z_i - g_i) % 12
            kw = f"{ZHI[k_i-2]}{ZHI[k_i-1]}"

            grid = {}
            for i in range(1, 10):
                s = star_map.get(i, "")
                s_meta = next((v for k,v in PHYSICAL_STARS.items() if v['name']==s), {})
                grid[str(i)] = {
                    "position": i,
                    "star": {"name": s, "astro": s_meta.get('astro', '')},
                    "god": {"name": god_map.get(i, "")},
                    "door": {"name": door_map.get(i, "") or "空"},
                    "stems": {"heaven": tp.get(i, ""), "earth": dp.get(i, "")}
                }

            resp = {
                "calendar": {
                    "gregorian": now.strftime("%Y-%m-%d %H:%M"),
                    "lunar": f"乙巳年 (Sim)", 
                    "ganzhi": f"乙{y_tai} 丁{m_build} {gz['day_str']} {gz['hour_str']}",
                    "kongwang": f"日空 {kw}",
                    "jieqi": dunjia['term']
                },
                "physics": {
                    "eot": f"{eot:.2f} min",
                    "location": {"lat": lat, "lon": lon},
                    "lmt_offset": f"{(lon-120)*4:.1f} min",
                    "hemisphere": "South" if is_south else "North",
                    "dubhe_angle": d_ang,
                    "jupiter_lon": jlon
                },
                "leaders": {
                    "zhifu": info['zhifu'],
                    "zhishi": info['zhishi'],
                    "ju": f"{'阳' if real_yang else '阴'}遁{dunjia['ju']}局 {dunjia['yuan']}",
                    "jiang": y_jiang
                },
                "grid": grid,
                "advantages": {"year": "木星定太岁", "month": "斗杓定月建", "hour": "真太阳时"},
                "meta": {}
            }
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode('utf-8'))
        except Exception as e:
            print(traceback.format_exc())
            self.send_error(500, str(e))

# 修复端口复用，防止重启报错
class ReuseTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

print(">>> V13.1 FIXED SERVER running on port 8000 <<<")
with ReuseTCPServer(("", PORT), V13Handler) as httpd:
    httpd.serve_forever()