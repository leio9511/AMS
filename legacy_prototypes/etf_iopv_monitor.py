import requests
import time
from datetime import datetime

# === CONFIGURATION ===
ETF_CODE = "sh513050"  # 中概互联ETF
ETF_NAME = "中概互联ETF"
HK_STOCK_CODE = "r_hk00700"  # 腾讯控股 (for reference)
HK_STOCK_NAME = "腾讯控股"
TENCENT_WEIGHT = 0.30  # 腾讯在中概互联中的权重 (约30%)
POLL_INTERVAL = 3  # 轮询间隔(秒)
PREMIUM_THRESHOLD = 0.5  # 溢价超过0.5%报警

def get_realtime_data(codes):
    """
    从腾讯接口获取实时行情数据
    codes: list, e.g. ['sh513050', 'r_hk00700']
    Returns: dict with parsed data
    """
    url = f"http://qt.gtimg.cn/q={','.join(codes)}"
    try:
        resp = requests.get(url, timeout=3)
        if resp.status_code != 200:
            return None
        content = resp.content.decode('gbk')
        return parse_tencent_data(content)
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None

def parse_tencent_data(raw_text):
    """
    解析腾讯接口返回的数据
    提取: ETF价格, IOPV, 溢价率, 腾讯价格
    """
    result = {}
    
    # 按分号分割每只股票的数据
    items = raw_text.strip().split(';')
    for item in items:
        if not item.strip():
            continue
        
        # 解析格式: v_sh513050="1~Name~Code~Price~..."
        import re
        match = re.search(r'v_([a-zA-Z0-9_]+)="(.*)"', item)
        if not match:
            continue
        
        var_name = match.group(1)  # e.g. "sh513050" or "r_hk00700"
        data_str = match.group(2)
        fields = data_str.split('~')
        
        if len(fields) < 50:
            continue
        
        # 解析关键字段
        stock_code = fields[2] if len(fields) > 2 else ""
        name = fields[1] if len(fields) > 1 else ""
        
        # 根据变量名判断是ETF还是港股
        if 'sh513050' in var_name or 'sz' in var_name.lower():
            # === ETF数据解析 ===
            try:
                price = float(fields[3]) if fields[3] else 0
            except:
                price = 0
            
            # IOPV位置 (通过之前的探测确认在倒数第6个字段附近)
            # 字段索引: 从0开始, 共约103个字段
            # 倒数第6个字段 (index -6 或 index 97/98)
            iopv = 0
            premium_pct = 0
            
            # 尝试多个可能的IOPV位置
            for idx in [-6, -5, -4, -7, 96, 97, 98]:
                try:
                    test_val = float(fields[idx])
                    # IOPV应该接近当前价格 (±10%以内)
                    if 0.8 * price < test_val < 1.2 * price:
                        iopv = test_val
                        break
                except:
                    continue
            
            # 如果没找到IOPV, 尝试查找溢价率字段
            # 有些接口直接提供溢价率百分比
            for idx in [40, 41, 42, 43, 44, 45]:
                try:
                    test_val = float(fields[idx])
                    # 溢价率通常是小数值 (如0.5表示0.5%)
                    if abs(test_val) < 10:  # 合理范围
                        premium_pct = test_val
                        break
                except:
                    continue
            
            result['etf'] = {
                'code': stock_code,
                'name': name,
                'price': price,
                'iopv': iopv,
                'premium_pct': premium_pct,
                'time': datetime.now().strftime("%H:%M:%S")
            }
            
        elif 'hk00700' in var_name.lower() or 'r_hk' in var_name.lower():
            # === 腾讯港股数据解析 ===
            try:
                price = float(fields[3]) if fields[3] else 0
            except:
                price = 0
            
            result['tencent'] = {
                'code': '00700',
                'name': name,
                'price_hkd': price,
                'time': datetime.now().strftime("%H:%M:%S")
            }
    
    return result

def calculate_metrics(data):
    """
    计算综合套利指标
    """
    if 'etf' not in data:
        return None
    
    etf = data['etf']
    tencent = data.get('tencent', {})
    
    # 核心指标: ETF溢价率
    price = etf['price']
    iopv = etf['iopv']
    
    # 如果找到了IOPV, 自己计算溢价率
    if iopv > 0:
        premium = (price - iopv) / iopv * 100  # 转为百分比
    else:
        premium = etf['premium_pct']  # 使用接口提供的溢价率
    
    # 构建结果
    metrics = {
        'etf_price': price,
        'iopv': iopv,
        'premium_pct': premium,
        'tencent_price_hkd': tencent.get('price_hkd', 0),
        'time': etf['time']
    }
    
    return metrics

def print_metrics(m):
    """
    格式化输出监控指标
    """
    time_str = m['time']
    price = m['etf_price']
    iopv = m['iopv']
    premium = m['premium_pct']
    tencent = m['tencent_price_hkd']
    
    # 判断信号
    signal = ""
    if premium > PREMIUM_THRESHOLD:
        signal = f"🔴 溢价过高! 建议操作: 卖出ETF / 买入腾讯"
    elif premium < -PREMIUM_THRESHOLD:
        signal = f"🟢 折价机会! 建议操作: 买入ETF / 卖出腾讯"
    else:
        signal = "⚪ 价格正常区间"
    
    print(f"[{time_str}] "
          f"ETF: {price:.3f} | "
          f"IOPV: {iopv:.4f} | "
          f"溢价: {premium:+.2f}% | "
          f"腾讯(HKD): {tencent:.2f} | "
          f"{signal}")

def main():
    print("=" * 70)
    print(f"ETF折溢价套利监控 - {ETF_NAME} vs {HK_STOCK_NAME}")
    print(f"监控标的: {ETF_CODE} (腾讯权重约{TENCENT_WEIGHT*100:.0f}%)")
    print(f"触发阈值: 溢价率 > {PREMIUM_THRESHOLD}% 或 < -{PREMIUM_THRESHOLD}%")
    print("=" * 70)
    print()
    
    codes = [ETF_CODE, HK_STOCK_CODE]
    
    while True:
        try:
            data = get_realtime_data(codes)
            if not data:
                time.sleep(POLL_INTERVAL)
                continue
            
            metrics = calculate_metrics(data)
            if metrics:
                print_metrics(metrics)
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 等待数据...")
                
        except KeyboardInterrupt:
            print("\n\n监控已停止。")
            break
        except Exception as e:
            print(f"异常: {e}")
        
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
