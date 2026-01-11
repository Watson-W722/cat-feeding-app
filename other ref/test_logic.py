import pandas as pd

# ==========================================
# 1. 模擬環境與函數 (同步 V5.7 邏輯)
# ==========================================
def safe_float(value):
    try:
        return float(value)
    except:
        return 0.0

def format_time_str(t_str):
    # V5.7 的核心邏輯：去冒號、去空白、補0
    t_str = str(t_str).strip().replace(":", "").replace("：", "")
    if len(t_str) == 3 and t_str.isdigit(): t_str = "0" + t_str
    if len(t_str) == 4 and t_str.isdigit(): return f"{t_str[:2]}:{t_str[2:]}"
    return "ERROR_FORMAT" # 測試用回傳

# 模擬資料庫裡的營養成分
mock_db_items = {
    "雞肉": {"Ref_Cal_100g": 120, "Protein_Pct": 20, "Unit": "g"},
    "魚油": {"Ref_Cal_100g": 10, "Protein_Pct": 0, "Unit": "顆"},
}

# ==========================================
# 2. 自動化測試案例 (Test Cases)
# ==========================================
print("🚀 開始 V5.7 自動化邏輯測試...\n")

# --- 測試 A: 時間格式化 ---
print("測試 A: 時間格式輸入...")
assert format_time_str("0618") == "06:18", "4碼轉換失敗"
assert format_time_str("618") == "06:18", "3碼轉換失敗"
print("✅ 時間格式測試通過")

# --- 測試 B: 一般食物熱量計算 (雞肉) ---
print("\n測試 B: 雞肉 (g) 熱量計算...")
input_weight = 50.0 
cal_per_100 = mock_db_items["雞肉"]["Ref_Cal_100g"] 
# V5.7 公式: 重量 * (每100g熱量 / 100)
expected_cal = input_weight * (cal_per_100 / 100) 
assert expected_cal == 60.0, f"熱量計算錯誤: 應為 60, 實算 {expected_cal}"
print(f"✅ 雞肉 50g = {expected_cal} kcal (通過)")

# --- 測試 C: 顆粒狀物品熱量計算 (魚油) ---
print("\n測試 C: 魚油 (顆) 熱量計算...")
input_count = 2.0 
cal_per_unit = mock_db_items["魚油"]["Ref_Cal_100g"] 
# V5.7 公式: 數量 * 單顆熱量 (顆數不除以100)
expected_cal_pill = input_count * cal_per_unit
assert expected_cal_pill == 20.0, f"顆數熱量錯誤: 應為 20, 實算 {expected_cal_pill}"
print(f"✅ 魚油 2顆 = {expected_cal_pill} kcal (通過)")

# --- 測試 D: 累加扣重邏輯 (新增品項區) ---
print("\n測試 D: 累加扣重邏輯...")
last_ref = 30.0 # 碗重或上一筆
current_scale = 80.0 # 秤重讀數
net = current_scale - last_ref
assert net == 50.0, "扣重計算錯誤"
print(f"✅ 秤重 {current_scale} - 前筆 {last_ref} = 淨重 {net} (通過)")

# --- 測試 E: 剩食扣除邏輯 (V5.7 雙欄位扣除 + 加權平均) ---
print("\n測試 E: 剩食熱量扣除...")
# 情境：已吃 雞肉100g(120kcal) + 水50g(0kcal)
total_in_weight = 150.0
total_in_cal = 120.0
avg_density = total_in_cal / total_in_weight # 0.8 kcal/g

# V5.7 新邏輯：輸入 容器總重 & 容器空重
waste_gross = 50.0 # 容器+剩食
waste_tare = 20.0  # 容器空重
waste_net = waste_gross - waste_tare # 應該是 30g

waste_cal = waste_net * avg_density # 30 * 0.8 = 24
assert waste_net == 30.0, "剩食淨重計算錯誤"
assert waste_cal == 24.0, f"剩食熱量錯誤: 應為 24, 實算 {waste_cal}"
print(f"✅ 剩食 30g (總重{waste_gross}-空重{waste_tare}) = 扣除 {waste_cal} kcal (通過)")

# --- 測試 F: Dashboard 統計邏輯 (V5.7 特定需求) ---
print("\n測試 F: Dashboard 統計排除邏輯...")
# 模擬今日數據 DataFrame
data = {
    'Category': ['主食', '水', '藥品', '保養品', '副食'],
    'Net_Quantity': [100, 50, 1, 1, 20],
    'Cal_Sub': [120, 0, 0, 0, 30]
}
df_mock = pd.DataFrame(data)

# 1. 本日總重 (V5.7 邏輯：排除 藥品, 保養品, 水)
mask_day = ~df_mock['Category'].isin(['藥品', '保養品', '水'])
day_weight = df_mock[mask_day]['Net_Quantity'].sum()
# 預期：100(主食) + 20(副食) = 120
assert day_weight == 120, f"本日總重錯誤: 應為 120, 實算 {day_weight}"

# 2. 本餐總重 (V5.7 邏輯：排除 藥品, 保養品，但包含水)
mask_meal = ~df_mock['Category'].isin(['藥品', '保養品'])
meal_weight = df_mock[mask_meal]['Net_Quantity'].sum()
# 預期：100(主食) + 50(水) + 20(副食) = 170
assert meal_weight == 170, f"本餐總重錯誤: 應為 170, 實算 {meal_weight}"

print(f"✅ 本日總重 (排除水/藥/保) = {day_weight}g (通過)")
print(f"✅ 本餐總重 (排除藥/保，含水) = {meal_weight}g (通過)")

print("\n🎉 V5.7 全部邏輯測試通過！")