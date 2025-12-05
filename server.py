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
# 0. 全局配置
# ==========================================
# 关键修复：适配云服务器端口
PORT = int(os.environ.get("PORT", 8000))

# [Formula.js] 飞盘九星 (1-9 全序)
STARS_FEI = ['天蓬', '天芮', '天冲', '天辅', '天禽', '天心', '天柱', '天任', '天英']

# [Formula.js] 飞盘八门 (8个，无中门)
# 对应宫位: 1, 2, 3, 4, 6, 7, 8, 9
DOORS_FEI = ['休门', '死门', '伤门', '杜门', '开门', '惊门', '生门', '景门']

# [Formula.js] 飞盘九神
GODS_FEI_YANG = ['值符', '螣蛇', '太阴', '六合', '勾陈', '太常', '朱雀', '九地', '九天']
GODS_FEI_YIN  = ['值符', '螣蛇', '太阴', '六合', '白虎', '太常', '玄武', '九地', '九天']

GAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

PHYSICAL_STARS_META = {
    "天蓬": "Dubhe", "天芮": "Merak", "天冲": "Phecda", "天辅": "Megrez",
    "天禽": "Alioth", "天心": "Mizar", "天柱": "Alkaid", "天任": "Alcor", "天英": "Mizar B"
}

# ==========================================
# 1. 茅山历法
# ==========================================
class LunarCore:
    def __init__(self):
        self.TERM_NAMES = [
            '冬至', '小寒', '大寒', '立春', '雨水', '惊蛰', '春分', '清明', '谷雨', '立夏', '小满', '芒种',
            '夏至', '小暑', '大暑', '立秋', '处暑', '白露', '秋分', '寒露', '霜降', '立冬', '小雪', '大雪'
        ]
        self.YANG_DUN = ['冬至','小寒','大寒','立春','雨水','惊蛰','春分','清明','谷雨','立夏','小满','芒种']
        self.JU_MAP = {
            '冬至': [1,7,4], '小寒': [2,8,5], '大寒': [3,9,6],
            '立春': [8,5,2], '雨水': [9,6,3], '惊蛰': [1,7,4],
            '春分': [3,9,6], '清明': [4,1,7], '谷雨': [5,2,8],
            '立夏': [4,1,7], '小满': [5,2,8], '芒种': [6,3,9],
            '夏至': [9,3,6], '小暑': [8,2,5], '大暑': [7,1,4],
            '立秋': [2,5,8], '处暑': [1,4,7], '白露': [9,3,6],
            '秋分': [7,1,4], '寒露': [6,9,3], '霜降': [5,8,2],
            '立冬': [6,9,3], '小雪': [5,8,2], '大雪': [4,7,1]
        }

    def get_gan_zhi(self, dt):
        base = datetime.datetime(2000, 1, 1)
        delta = (dt - base).days
        day_idx = (delta + 54) % 60
        d_gan_idx = day_idx % 10
        h_zhi_idx = int((dt.hour + 1) // 2) % 12
        h_gan_idx = ((d_gan_idx % 5) * 2 + h_zhi_idx) % 10
        y_idx = (dt.year - 1984) % 60
        if y_idx < 0: y_idx += 60
        return {
            "day_str": f"{GAN[day_idx%10]}{ZHI[day_idx%12]}",
            "hour_str": f"{GAN[h_gan_idx]}{ZHI[h_zhi_idx]}",
            "d_idx": day_idx,
            "h_gan": GAN[h_gan_idx],
            "h_zhi": ZHI[h_zhi_idx],
            "h_zhi_idx": h_zhi_idx,
            "y_str": f"{GAN[y_idx%10]}{ZHI[y_idx%12]}",
            "y_gan_idx": y_idx % 10
        }

    def get_maoshan_ju(self, solar_lon, day_idx):
        lon = solar_lon % 360
        offset = (lon - 270) % 360
        term_idx = int(offset // 15)
        term_name = self.TERM_NAMES[term_idx]
        futou_idx = day_idx - (day_idx % 5)
        futou_zhi = futou_idx % 12
        yuan_idx = 2; yuan_name = "下元"
        if futou_zhi in [0, 6, 3, 9]: yuan_idx=0; yuan_name="上元"
        elif futou_zhi in [2, 8, 5, 11]: yuan_idx=1; yuan_name="中元"
        
        is_yang = term_name in self.YANG_DUN
        ju = self.JU_MAP.get(term_name, [1,1,1])[yuan_idx]
        return {"ju": ju, "is_yang": is_yang, "term": term_name, "yuan": yuan_name}

# ==========================================
# 2. V12 物理引擎
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
        # 关键修复：使用 datetime.timedelta
        return dt + datetime.timedelta(minutes=eot+offset), eot

    def get_solar_longitude(self, dt):
        delta = dt - datetime.datetime(2000, 1, 1, 12, 0)
        n = delta.days + delta.seconds / 86400.0
        L = (280.460 + 0.9856474 * n) % 360
        g = (357.528 + 0.9856003 * n) % 360
        g_rad = math.radians(g)
        lambda_sun = L + 1.915 * math.sin(g_rad) + 0.020 * math.sin(2 * g_rad)
        return lambda_sun % 360

    def get_astronomy(self, tst):
        solar_lon = self.get_solar_longitude(tst)
        month_offset = int(((solar_lon - 315) % 360) // 30)
        m_idx = (2 + month_offset) % 12
        month_build = ZHI[m_idx]
        angle = (solar_lon + 180) % 360 
        j_off = int(solar_lon/30)
        jiangs = ["戌", "酉", "申", "未", "午", "巳", "辰", "卯", "寅", "丑", "子", "亥"]
        return solar_lon, 0, month_build, angle, "", jiangs[j_off]

    def get_di_pan(self, ju, is_yang):
        dp = {}
        start_pos = ju 
        for i, stem in enumerate(self.stems):
            if is_yang:
                pos = ((start_pos - 1 + i) % 9) + 1
            else:
                pos = ((start_pos - 1 - i) % 9) + 1
            dp[pos] = stem
        return dp

    def deduce(self, ju, is_yang, h_gan, h_zhi_idx):
        dp = self.get_di_pan(ju, is_yang)
        
        # 1. 找旬首
        g_i = GAN.index(h_gan)
        head_zhi_idx = (h_zhi_idx - g_i) % 12
        xun_map = {0:'戊', 10:'己', 8:'庚', 6:'辛', 4:'壬', 2:'癸'}
        xun_stem = xun_map.get(head_zhi_idx, '戊')
        
        # 2. 旬首落宫
        pos_xun = 1
        for p, s in dp.items():
            if s == xun_stem: pos_xun = p; break
            
        raw_stars = {1:"天蓬", 2:"天芮", 3:"天冲", 4:"天辅", 5:"天禽", 6:"天心", 7:"天柱", 8:"天任", 9:"天英"}
        raw_doors = {1:"休门", 2:"死门", 3:"伤门", 4:"杜门", 6:"开门", 7:"惊门", 8:"生门", 9:"景门"}
        
        zhifu_name = raw_stars.get(pos_xun, "天禽")
        
        if pos_xun == 5:
            zhishi_name = "死门"
            pos_door_start = 2 # 阳8阴2修正逻辑在 deduce 外部的 steps 处理，这里暂定起点
            # 修正：按照飞盘逻辑，如果旬首在5，值使从5开始数，但落入5时变通
            pos_door_start = 5 
        else:
            zhishi_name = raw_doors.get(pos_xun, "死门")
            pos_door_start = pos_xun
            
        # 3. 值符落宫 (随时干)
        target_stem = h_gan
        if h_gan == '甲': target_stem = xun_stem
        
        star_dest = 1
        for p, s in dp.items():
            if s == target_stem: star_dest = p; break
            
        # 4. 值使落宫 (随时支)
        # 飞盘数宫法：123456789 (阳) / 987654321 (阴)
        # 从 pos_door_start 开始，数 steps 步
        
        steps = (h_zhi_idx - head_zhi_idx) % 12
        
        door_dest = pos_door_start
        if is_yang:
            for _ in range(steps):
                door_dest = (door_dest % 9) + 1
        else:
            for _ in range(steps):
                door_dest = door_dest - 1
                if door_dest < 1: door_dest = 9
        
        # 飞盘核心修正：值使门如果落入5宫，阳遁寄8，阴遁寄2
        if door_dest == 5:
            door_dest = 8 if is_yang else 2
                
        return {
            "zhifu": zhifu_name,
            "zhishi": zhishi_name,
            "star_pos": star_dest,
            "door_pos": door_dest
        }

# --- 飞盘排布函数 ---
def distribute_feipan(leader, start_pos, is_yang, queue, skip_five=False):
    path = []
    curr = start_pos
    count = 8 if skip_five else 9
    direction = 1 if is_yang else -1
    
    for _ in range(count):
        path.append(curr)
        next_val = ((curr + direction - 1) % 9) + 1
        if skip_five and next_val == 5:
            next_val = ((next_val + direction - 1) % 9) + 1
        curr = next_val
        
    try:
        leader_idx = queue.index(leader)
    except:
        leader_idx = 0
        
    result = {}
    for k in range(len(path)):
        palace = path[k]
        item_idx = (leader_idx + k) % len(queue)
        result[palace] = queue[item_idx]
    return result

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
        self.send_response(200); self.end_headers()

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
            slon, jlon, m_build, d_ang, _, y_jiang = engine.get_astronomy(tst)
            
            gz = lunar.get_gan_zhi(tst)
            y_gan_i = gz['y_gan_idx']; m_zhi_i = ZHI.index(m_build)
            month_offset = m_zhi_i - 2
            if month_offset < 0: month_offset += 12
            m_gan_i = ((y_gan_i % 5) * 2 + 2 + month_offset) % 10
            full_ganzhi = f"{gz['y_str']} {GAN[m_gan_i]}{m_build} {gz['day_str']} {gz['hour_str']}"
            
            dunjia = lunar.get_maoshan_ju(slon, gz['d_idx'])
            real_yang = dunjia['is_yang']
            if is_south: real_yang = not real_yang; dunjia['desc'] += " (南)"
            
            dp = engine.get_di_pan(dunjia['ju'], real_yang)
            info = engine.deduce(dunjia['ju'], real_yang, gz['h_gan'], gz['h_zhi_idx'])
            
            # 飞盘排布
            star_map = distribute_feipan(info['zhifu'], info['star_pos'], real_yang, STARS_FEI, False)
            # 八门 (跳过5)
            door_map = distribute_feipan(info['zhishi'], info['door_pos'], real_yang, DOORS_FEI, True)
            # 九神
            gods_queue = GODS_FEI_YANG if real_yang else GODS_FEI_YIN
            god_map = distribute_feipan("值符", info['star_pos'], real_yang, gods_queue, False)
            
            # 天盘干
            base_star_origin = {
                "天蓬":1, "天芮":2, "天冲":3, "天辅":4, "天禽":5, 
                "天心":6, "天柱":7, "天任":8, "天英":9
            }
            tp = {}
            for pos, s_name in star_map.items():
                orig = base_star_origin.get(s_name, 1)
                tp[pos] = dp.get(orig, "")

            kw_idx = (ZHI.index(gz['day_str'][1]) - GAN.index(gz['day_str'][0])) % 12
            kw = f"{ZHI[kw_idx-2]}{ZHI[kw_idx-1]}"

            grid = {}
            for i in range(1, 10):
                s_name = star_map.get(i, "")
                astro = PHYSICAL_STARS_META.get(s_name, "")
                
                grid[str(i)] = {
                    "position": i,
                    "star": {"name": s_name, "astro": astro},
                    "god": {"name": god_map.get(i, "")},
                    "door": {"name": door_map.get(i, "")},
                    "stems": {"heaven": tp.get(i, ""), "earth": dp.get(i, "")}
                }

            resp = {
                "calendar": {
                    "gregorian": now.strftime("%Y-%m-%d %H:%M"),
                    "lunar": f"{gz['y_str']}年 ({dunjia['term']})",
                    "ganzhi": full_ganzhi,
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

class ReuseTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

print(f">>> V16.1 FEIPAN FINAL SERVER running on port {PORT} <<<")
with ReuseTCPServer(("", PORT), V13Handler) as httpd:
    httpd.serve_forever()