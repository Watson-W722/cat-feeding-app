# Python 程式碼 V8.1 (強制渲染修復版)

iimport streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import uuid

# --- 1. 設定頁面 ---
st.set_page_config(page_title="大文餵食紀錄", page_icon="🐱", layout="wide")

# --- 小工具 ---
def safe_float(value):
    try:
        if value is None: return 0.0
        return float(value)
    except (ValueError, TypeError):
        return 0.0

def get_tw_time():
    tz_tw = timezone(timedelta(hours=8))
    return datetime.now(tz_tw)

def format_time_str(t_str):
    t_str = str(t_str).strip().replace(":", "").replace("：", "")
    if len(t_str) == 3 and t_str.isdigit():
        t_str = "0" + t_str
    if len(t_str) == 4 and t_str.isdigit():
        return f"{t_str[:2]}:{t_str[2:]}"
    return t_str if ":" in str(t_str) else get_tw_time().strftime("%H:%M")

# [V7.5] 清洗重複完食紀錄工具
def clean_duplicate_finish_records(df):
    if df.empty: return df
    mask_finish = df['ItemID'].isin(['WASTE', 'FINISH'])
    df_others = df[~mask_finish]
    df_finish = df[mask_finish]
    if df_finish.empty: return df
    df_finish_clean = df_finish.drop_duplicates(subset=['Meal_Name'], keep='last')
    return pd.concat([df_others, df_finish_clean], ignore_index=True)

# [V7.0] 智能權重拆分計算
def calculate_intake_breakdown(df):
    if df.empty: return 0.0, 0.0
    if 'Category' in df.columns: df['Category'] = df['Category'].astype(str).str.strip()
    exclude_list = ['藥品', '保養品']
    df_calc = df[~df['Category'].isin(exclude_list)].copy()
    if df_calc.empty: return 0.0, 0.0

    df_input = df_calc[df_calc['Net_Quantity'] > 0]
    df_waste = df_calc[df_calc['Net_Quantity'] < 0]
    
    water_cats = ['水', '飲用水']
    input_water = df_input[df_input['Category'].isin(water_cats)]['Net_Quantity'].sum()
    input_food = df_input[~df_input['Category'].isin(water_cats)]['Net_Quantity'].sum()
    total_input = input_water + input_food
    total_waste = df_waste['Net_Quantity'].sum()
    
    if total_input > 0:
        ratio_water = input_water / total_input
        ratio_food = input_food / total_input
    else:
        ratio_water = 0.0
        ratio_food = 1.0
        
    final_water_net = input_water + (total_waste * ratio_water)
    final_food_net = input_food + (total_waste * ratio_food)
    return final_food_net, final_water_net

# --- [V7.8] UI 生成函數 (HTML/CSS) ---
def render_dashboard_html(day_stats, meal_stats, supp_list, med_list):
    icons = {
        "flame": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.1.2-2.2.6-3.3a1 1 0 0 0 2.1.7z"></path></svg>',
        "utensils": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/><path d="M7 2v20"/><path d="M21 15V2v0a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"/></svg>',
        "droplets": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 16.3c2.2 0 4-1.83 4-4.05 0-1.16-.57-2.26-1.71-3.19S7.29 6.75 7 5.3c-.29 1.45-1.14 2.84-2.29 3.76S3 11.1 3 12.25c0 2.22 1.8 4.05 4 4.05z"/><path d="M12.56 6.6A10.97 10.97 0 0 0 14 3.02c.5 2.5 2 4.9 4 6.5s3 3.5 3 5.5a6.98 6.98 0 0 1-11.91 4.97"/></svg>',
        "beef": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12.5" cy="8.5" r="2.5"/><path d="M12.5 2a6.5 6.5 0 0 0-6.22 4.6c-1.1 3.13-.78 6.43 1.48 9.17l2.92 2.92c.65.65 1.74.65 2.39 0l.97-.97a6 6 0 0 1 4.24-1.76h.04a6 6 0 0 0 3.79-1.35l.81-.81a2.5 2.5 0 0 0-3.54-3.54l-.47.47a1.5 1.5 0 0 1-2.12 0l-.88-.88a2.5 2.5 0 0 1 0-3.54l.84-.84c.76-.76.88-2 .2-2.86A6.5 6.5 0 0 0 12.5 2Z"/></svg>',
        "dna": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 15c6.638 0 12-5.362 12-12"/><path d="M10 21c6.638 0 12-5.362 12-12"/><path d="m2 3 20 18"/><path d="M12.818 8.182a4.92 4.92 0 0 0-1.636-1.636"/><path d="M16.364 11.728a9.862 9.862 0 0 0-3.092-3.092"/><path d="M9.272 15.364a9.862 9.862 0 0 0-3.092-3.092"/><path d="M12.818 18.91a4.92 4.92 0 0 0-1.636-1.636"/></svg>',
        "pill": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m10.5 20.5 10-10a4.95 4.95 0 1 0-7-7l-10 10a4.95 4.95 0 1 0 7 7Z"/><path d="m8.5 8.5 7 7"/></svg>',
        "leaf": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.77 10-10 10Z"/><path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/></svg>',
        "activity": '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>'
    }

    style = """
    <style>
        .dashboard-card { background: white; border-radius: 16px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 1px solid #f1f5f9; margin-bottom: 20px; }
        .section-title { font-size: 16px; font-weight: 700; color: #334155; display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
        .section-icon { padding: 6px; border-radius: 8px; display: flex; align-items: center; justify-content: center; }
        .grid-stats { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
        @media (max-width: 768px) { .grid-stats { grid-template-columns: repeat(2, 1fr); } }
        .stat-item { background: white; border: 1px solid #f1f5f9; border-radius: 12px; padding: 12px; display: flex; flex-direction: column; justify-content: space-between; }
        .stat-header { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; font-size: 12px; font-weight: 500; color: #64748b; }
        .stat-icon { padding: 4px; border-radius: 6px; display: flex; align-items: center; justify-content: center; }
        .stat-value { font-size: 20px; font-weight: 700; color: #1e293b; line-height: 1.2; }
        .stat-unit { font-size: 12px; font-weight: 500; color: #94a3b8; margin-left: 2px; }
        .tag-container { display: flex; flex-wrap: wrap; gap: 8px; }
        .tag { display: inline-flex; align-items: center; padding: 4px 10px; border-radius: 8px; font-size: 13px; font-weight: 500; border: 1px solid transparent; }
        .tag-count { background: rgba(255,255,255,0.8); padding: 1px 5px; border-radius: 4px; font-size: 10px; font-weight: 700; margin-left: 6px; }
        .bg-orange { background: #fff7ed; color: #f97316; }
        .bg-blue { background: #eff6ff; color: #3b82f6; }
        .bg-cyan { background: #ecfeff; color: #06b6d4; }
        .bg-red { background: #fef2f2; color: #ef4444; }
        .bg-yellow { background: #fefce8; color: #eab308; }
        .tag-green { background: #ecfdf5; color: #047857; border-color: #d1fae5; }
        .tag-red { background: #fff1f2; color: #be123c; border-color: #ffe4e6; }
        .bar-bg { height: 6px; width: 100%; background: #f1f5f9; border-radius: 99px; margin-top: 10px; overflow: hidden; }
        .bar-fill { height: 100%; border-radius: 99px; }
    </style>
    """

    def get_stat_html(icon, label, value, unit, color_class, bar_color, percent=0):
        bar_html = f'<div class="bar-bg"><div class="bar-fill" style="width: {min(percent, 100)}%; background: {bar_color};"></div></div>' if percent > 0 else '<div style="height:6px; margin-top:10px"></div>'
        return f"""
        <div class="stat-item">
            <div>
                <div class="stat-header"><div class="stat-icon {color_class}">{icons[icon]}</div>{label}</div>
                <div style="display:flex; align-items:baseline;"><span class="stat-value">{value}</span><span class="stat-unit">{unit}</span></div>
            </div>
            {bar_html}
        </div>
        """

    def get_tag_html(items, type_class, icon_key):
        if not items: return '<span style="color:#94a3b8; font-size:13px;">無</span>'
        html = ""
        for item in items:
            html += f"""<span class="tag {type_class}">{icons[icon_key]} {item['name']}<span class="tag-count">x{int(item['count'])}</span></span>"""
        return html

    # 本日
    daily_html = f"""
    <div class="dashboard-card">
        <div class="section-title"><div class="section-icon bg-orange">{icons['activity']}</div>本日總計</div>
        <div class="grid-stats">
            {get_stat_html("flame", "熱量", int(day_stats['cal']), "kcal", "bg-orange", "#f97316", day_stats['cal']/250)}
            {get_stat_html("utensils", "食物", f"{day_stats['food']:.1f}", "g", "bg-blue", "#3b82f6")}
            {get_stat_html("droplets", "飲水", f"{day_stats['water']:.1f}", "ml", "bg-cyan", "#06b6d4")}
            {get_stat_html("beef", "蛋白質", f"{day_stats['prot']:.1f}", "g", "bg-red", "#ef4444")}
            {get_stat_html("dna", "脂肪", f"{day_stats['fat']:.1f}", "g", "bg-yellow", "#eab308")}
        </div>
    </div>
    """
    # 本餐
    meal_html = f"""
    <div class="dashboard-card">
        <div class="section-title">
            <div class="section-icon bg-blue">{icons['utensils']}</div>本餐小計
            <span style="margin-left:auto; font-size:12px; background:#eff6ff; color:#3b82f6; padding:2px 8px; border-radius:99px; font-weight:600;">{meal_stats['name']}</span>
        </div>
        <div class="grid-stats">
            {get_stat_html("flame", "熱量", int(meal_stats['cal']), "kcal", "bg-orange", "#f97316")}
            {get_stat_html("utensils", "食物", f"{meal_stats['food']:.1f}", "g", "bg-blue", "#3b82f6")}
            {get_stat_html("droplets", "飲水", f"{meal_stats['water']:.1f}", "ml", "bg-cyan", "#06b6d4")}
            {get_stat_html("beef", "蛋白質", f"{meal_stats['prot']:.1f}", "g", "bg-red", "#ef4444")}
            {get_stat_html("dna", "脂肪", f"{meal_stats['fat']:.1f}", "g", "bg-yellow", "#eab308")}
        </div>
    </div>
    """
    # 藥品
    supp_med_html = f"""
    <div class="dashboard-card">
        <div class="section-title"><div class="section-icon bg-green" style="background:#ecfdf5; color:#047857;">{icons['pill']}</div>保養與藥品紀錄</div>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px;">
            <div><div style="font-size:11px; font-weight:700; color:#94a3b8; margin-bottom:8px; text-transform:uppercase;">保養品清單</div><div class="tag-container">{get_tag_html(supp_list, "tag-green", "leaf")}</div></div>
            <div><div style="font-size:11px; font-weight:700; color:#94a3b8; margin-bottom:8px; text-transform:uppercase;">藥品清單</div><div class="tag-container">{get_tag_html(med_list, "tag-red", "pill")}</div></div>
        </div>
    </div>
    """
    return style + daily_html + meal_html + supp_med_html

# --- 連線設定 ---
@st.cache_resource
def init_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

try:
    client = init_connection()
    spreadsheet = client.open("DaWen daily record")
    sheet_log = spreadsheet.worksheet("Log_Data")
    sheet_db = spreadsheet.worksheet("DB_Items")
except Exception as e:
    st.error(f"連線失敗：{e}")
    st.stop()

# --- 讀取資料 ---
@st.cache_data(ttl=5)
def load_data():
    db_data = sheet_db.get_all_records()
    log_data = sheet_log.get_all_records()
    return pd.DataFrame(db_data), pd.DataFrame(log_data)

df_items, df_log = load_data()

# 初始化 Mapping
if not df_items.empty:
    df_items.columns = [c.strip() for c in df_items.columns]
    item_map = dict(zip(df_items['Item_Name'], df_items['ItemID']))
    cal_map = dict(zip(df_items['Item_Name'], df_items['Ref_Cal_100g']))
    prot_map = dict(zip(df_items['Item_Name'], df_items['Protein_Pct']))
    fat_map = dict(zip(df_items['Item_Name'], df_items['Fat_Pct']))
    phos_map = dict(zip(df_items['Item_Name'], df_items['Phos_Pct']))
    cat_map = dict(zip(df_items['Item_Name'], df_items['Category']))
    unit_map = dict(zip(df_items['Item_Name'], df_items['Unit_Type']))
else:
    st.error("讀取不到 DB_Items")
    st.stop()

# ==========================================
#      邏輯函數區 (Callback)
# ==========================================

def reset_meal_inputs():
    st.session_state.scale_val = None
    st.session_state.check_zero = False
    st.session_state.waste_gross = None
    st.session_state.waste_tare = None
    st.session_state.finish_radio = "全部吃光 (盤光光)"

def add_to_cart_callback(bowl_w, last_ref_w, last_ref_n):
    category = st.session_state.get('cat_select', '請選擇...')
    item_name = st.session_state.get('item_select', '請先選類別')
    raw_scale = st.session_state.get('scale_val')
    scale_reading = safe_float(raw_scale)
    is_zeroed = st.session_state.get('check_zero', False)
    
    if category == "請選擇..." or item_name == "請先選類別" or scale_reading <= 0:
        return

    unit = unit_map.get(item_name, "g")
    net_weight = 0.0
    db_scale_reading = scale_reading
    
    if unit in ["顆", "粒", "錠", "膠囊", "次"]:
        net_weight = scale_reading
        db_scale_reading = last_ref_w 
    else:
        if is_zeroed:
            net_weight = scale_reading
        else:
            if scale_reading < last_ref_w:
                return 
            net_weight = scale_reading - last_ref_w

    item_id = item_map.get(item_name, "")
    cat_real = cat_map.get(item_name, "")
    cal_val = safe_float(cal_map.get(item_name, 0))
    prot_val = safe_float(prot_map.get(item_name, 0))
    fat_val = safe_float(fat_map.get(item_name, 0))
    phos_val = safe_float(phos_map.get(item_name, 0))

    if unit in ["顆", "粒", "錠", "膠囊", "次"]:
        cal = net_weight * cal_val
        prot = net_weight * prot_val
        fat = net_weight * fat_val
        phos = net_weight * phos_val
    else:
        cal = net_weight * cal_val / 100
        prot = net_weight * prot_val / 100
        fat = net_weight * fat_val / 100
        phos = net_weight * phos_val / 100

    st.session_state.cart.append({
        "Category": cat_real,
        "ItemID": item_id,
        "Item_Name": item_name,
        "Scale_Reading": db_scale_reading,
        "Bowl_Weight": bowl_w,
        "Net_Quantity": net_weight,
        "Cal_Sub": cal,
        "Prot_Sub": prot,
        "Fat_Sub": fat,
        "Phos_Sub": phos,
        "Unit": unit
    })
    
    st.session_state.scale_val = None
    st.session_state.check_zero = False
    st.session_state.meal_open = False
    st.session_state.just_saved = True

def save_finish_callback(finish_type, waste_net, waste_cal, bowl_w, meal_n, finish_time_str, record_date_obj):
    if finish_type == "有剩餘 (需秤重)" and waste_net <= 0:
        st.session_state.finish_error = "剩餘重量計算錯誤，請檢查輸入數值。"
        return

    str_date = record_date_obj.strftime("%Y/%m/%d")
    str_time_finish = f"{finish_time_str}:00"
    timestamp = f"{str_date} {str_time_finish}"
    
    final_waste_net = -waste_net if finish_type == "有剩餘 (需秤重)" else 0
    final_waste_cal = -waste_cal if finish_type == "有剩餘 (需秤重)" else 0
    item_id_code = "WASTE" if finish_type == "有剩餘 (需秤重)" else "FINISH"
    category_code = "剩食" if finish_type == "有剩餘 (需秤重)" else "完食"

    row = [
        str(uuid.uuid4()), timestamp, str_date, str_time_finish, meal_n,
        item_id_code, category_code, 0, bowl_w, 
        final_waste_net, final_waste_cal, 
        0, 0, 0, "",
        "完食紀錄", finish_time_str
    ]
    
    try:
        current_data = sheet_log.get_all_values()
        header = current_data[0]
        try:
            date_idx = header.index('Date')
            meal_idx = header.index('Meal_Name')
            item_idx = header.index('ItemID')
        except ValueError:
            date_idx = 2
            meal_idx = 4
            item_idx = 5

        rows_to_delete = []
        for i in range(len(current_data) - 1, 0, -1):
            r = current_data[i]
            if (r[date_idx] == str_date and 
                r[meal_idx] == meal_n and 
                r[item_idx] in ['WASTE', 'FINISH']):
                rows_to_delete.append(i + 1)
        
        for r_idx in rows_to_delete:
            sheet_log.delete_rows(r_idx)
            
        sheet_log.append_row(row)
        st.toast("✅ 完食紀錄已更新 (舊紀錄已覆蓋)")
        load_data.clear()
        
        st.session_state.waste_gross = None
        st.session_state.waste_tare = None
        st.session_state.finish_error = None
        
        st.session_state.just_saved = True
    except Exception as e:
        st.session_state.finish_error = f"寫入失敗：{e}"

def clear_finish_inputs_callback():
    st.session_state.waste_gross = None
    st.session_state.waste_tare = None

# ==========================================
#      UI 佈局開始
# ==========================================
st.title("🐱 大文餵食紀錄")

# 初始化狀態
if 'dash_open' not in st.session_state: st.session_state.dash_open = False
if 'meal_open' not in st.session_state: st.session_state.meal_open = False
if 'just_saved' not in st.session_state: st.session_state.just_saved = False
if 'finish_radio' not in st.session_state: st.session_state.finish_radio = "全部吃光 (盤光光)"
if 'nav_mode' not in st.session_state: st.session_state.nav_mode = "➕ 新增食物/藥品"
if 'finish_error' not in st.session_state: st.session_state.finish_error = None

# 自動捲動
if st.session_state.just_saved:
    js = """
    <script>
        var body = window.parent.document.querySelector(".main");
        body.scrollTop = 0;
    </script>
    """
    components.html(js, height=0)
    st.session_state.just_saved = False

# --- 側邊欄 ---
with st.sidebar:
    st.header("⚙️ 設定")
    tw_now = get_tw_time()
    record_date = st.date_input("📅 日期", tw_now)
    str_date_filter = record_date.strftime("%Y/%m/%d")
    
    default_sidebar_time = tw_now.strftime("%H%M")
    raw_record_time = st.text_input("🕒 時間 (如 0618)", value=default_sidebar_time)
    record_time_str = format_time_str(raw_record_time)
    st.caption(f"將記錄為：{record_time_str}")
    st.caption("輸入數字後，點擊空白處即可生效")
    
    if st.button("🔄 重新整理數據"):
        load_data.clear()
        st.rerun()

# --- 1. 數據準備 ---
df_today = pd.DataFrame()
day_stats = {'cal':0, 'food':0, 'water':0, 'prot':0, 'fat':0}
meal_stats = {'name': '尚未選擇', 'cal':0, 'food':0, 'water':0, 'prot':0, 'fat':0}
supp_list = []
med_list = []

if not df_log.empty:
    df_today = df_log[df_log['Date'] == str_date_filter].copy()
    if not df_today.empty:
        if 'Category' in df_today.columns:
            df_today['Category'] = df_today['Category'].astype(str).str.strip()
        
        for col in ['Cal_Sub', 'Net_Quantity', 'Prot_Sub', 'Fat_Sub']:
            df_today[col] = pd.to_numeric(df_today[col], errors='coerce').fillna(0)
        
        df_today = clean_duplicate_finish_records(df_today)
        
        day_food_net, day_water_net = calculate_intake_breakdown(df_today)
        day_stats['cal'] = df_today['Cal_Sub'].sum()
        day_stats['food'] = day_food_net
        day_stats['water'] = day_water_net
        day_stats['prot'] = df_today['Prot_Sub'].sum()
        day_stats['fat'] = df_today['Fat_Sub'].sum()

        if 'Category' in df_today.columns:
            df_supp = df_today[df_today['Category'] == '保養品']
            if not df_supp.empty:
                counts = df_supp.groupby('Item_Name')['Net_Quantity'].sum()
                supp_list = [{'name': k, 'count': v} for k, v in counts.items()]
            
            df_med = df_today[df_today['Category'] == '藥品']
            if not df_med.empty:
                counts = df_med.groupby('Item_Name')['Net_Quantity'].sum()
                med_list = [{'name': k, 'count': v} for k, v in counts.items()]

# --- 2. Dashboard (React Style) ---
with st.expander("📊 今日數據統計 (點擊收合)", expanded=st.session_state.dash_open):
    dashboard_ph = st.empty()

# --- 3. 餐別設定 ---
recorded_meals = []
if not df_today.empty:
    recorded_meals = df_today['Meal_Name'].unique().tolist()

meal_options = ["第一餐", "第二餐", "第三餐", "第四餐", "第五餐", 
                "第六餐", "第七餐", "第八餐", "第九餐", "第十餐", "點心"]

default_meal_name = meal_options[0]
for m in meal_options:
    if m not in recorded_meals:
        default_meal_name = m
        break

if 'meal_selector' not in st.session_state:
    st.session_state.meal_selector = default_meal_name

with st.expander("🥣 餐別與碗重設定 (點擊收合)", expanded=st.session_state.meal_open):
    c_meal, c_bowl = st.columns(2)
    with c_meal:
        def meal_formatter(m):
            return f"{m} (已記)" if m in recorded_meals else m
        
        meal_name = st.selectbox(
            "🍽️ 餐別", 
            meal_options, 
            format_func=meal_formatter,
            key="meal_selector",
            on_change=reset_meal_inputs
        )
    
    last_bowl = 30.0
    df_meal = pd.DataFrame()
    
    if not df_today.empty:
        mask_meal = (df_today['Meal_Name'] == meal_name)
        df_meal = df_today[mask_meal]
        if not df_meal.empty:
            try:
                last_bowl = float(df_meal.iloc[-1]['Bowl_Weight'])
            except:
                pass
    
    with c_bowl:
        bowl_weight = st.number_input("🥣 碗重 (g)", value=last_bowl, step=0.1, format="%.1f")

    if not df_meal.empty:
        with st.expander(f"📜 查看 {meal_name} 已記錄明細"):
            view_df = df_meal[['Item_Name', 'Net_Quantity', 'Cal_Sub', 'Time']].copy()
            def append_time_to_finish(row):
                if '完食' in str(row['Item_Name']):
                    time_str = str(row['Time'])[:5]
                    return f"{row['Item_Name']} {time_str}"
                return row['Item_Name']
            view_df['Item_Name'] = view_df.apply(append_time_to_finish, axis=1)
            view_df = view_df.drop(columns=['Time'])
            view_df.columns = ['品名', '數量/重量', '熱量']
            st.dataframe(view_df, use_container_width=True, hide_index=True)

# --- 計算本餐數據並渲染 Dashboard ---
meal_stats['name'] = meal_name
if not df_meal.empty:
    for col in ['Cal_Sub', 'Net_Quantity', 'Prot_Sub', 'Fat_Sub']:
        df_meal[col] = pd.to_numeric(df_meal[col], errors='coerce').fillna(0)
    
    df_meal_clean = clean_duplicate_finish_records(df_meal)
    
    m_food, m_water = calculate_intake_breakdown(df_meal_clean)
    meal_stats['food'] = m_food
    meal_stats['water'] = m_water
    meal_stats['cal'] = df_meal_clean['Cal_Sub'].sum()
    meal_stats['prot'] = df_meal_clean['Prot_Sub'].sum()
    meal_stats['fat'] = df_meal_clean['Fat_Sub'].sum()

# 渲染 HTML Dashboard (包含 unsafe_allow_html=True)
html_content = render_dashboard_html(day_stats, meal_stats, supp_list, med_list)
dashboard_ph.markdown(html_content, unsafe_allow_html=True)

# ==========================================
#      主畫面區塊 3：操作區
# ==========================================

if 'cart' not in st.session_state:
    st.session_state.cart = []

last_reading_db = bowl_weight
last_item_db = "碗"
if not df_meal.empty:
    try:
        df_food_only = df_meal[~df_meal['ItemID'].isin(['WASTE', 'FINISH'])]
        if not df_food_only.empty:
            last_reading_db = float(df_food_only.iloc[-1]['Scale_Reading'])
            last_item_db = df_food_only.iloc[-1]['Item_Name']
    except:
        pass

if len(st.session_state.cart) > 0:
    last_ref_weight = st.session_state.cart[-1]['Scale_Reading']
    last_ref_name = st.session_state.cart[-1]['Item_Name']
else:
    last_ref_weight = last_reading_db
    last_ref_name = last_item_db

nav_mode = st.radio(
    "操作模式", 
    ["➕ 新增食物/藥品", "🏁 完食/紀錄剩餘"], 
    horizontal=True,
    label_visibility="collapsed",
    key="nav_mode"
)

# --- 模式 1: 新增 ---
if nav_mode == "➕ 新增食物/藥品":
    st.markdown(f"##### 🍽️ 編輯：{meal_name}")
    
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            unique_cats = ["請選擇..."] + list(df_items['Category'].unique())
            def on_cat_change(): st.session_state.scale_val = None
            filter_cat = st.selectbox("1. 類別", unique_cats, key="cat_select", on_change=on_cat_change)
            
            if filter_cat == "請選擇..." or filter_cat == "全部":
                filtered_items = []
                if filter_cat == "全部": filtered_items = df_items['Item_Name'].tolist()
            else:
                filtered_items = df_items[df_items['Category'] == filter_cat]['Item_Name'].tolist()

        with c2:
            item_name = st.selectbox("2. 品名", filtered_items if filtered_items else ["請先選類別"], key="item_select")

        unit = unit_map.get(item_name, "g")
        
        c3, c4 = st.columns(2)
        with c3:
            if 'scale_val' not in st.session_state: st.session_state.scale_val = None
            
            if unit in ["顆", "粒", "錠", "膠囊", "次"]:
                scale_reading_ui = st.number_input(f"3. 數量 ({unit})", step=1.0, key="scale_val", value=None, placeholder="輸入數量")
                is_zeroed_ui = True 
            else:
                scale_reading_ui = st.number_input("3. 秤重讀數 (g)", step=0.1, format="%.1f", key="scale_val", value=None, placeholder="輸入重量")
                st.caption(f"前筆: {last_ref_weight} g ({last_ref_name})")
                is_zeroed_ui = st.checkbox("⚖️ 已歸零 / 單獨秤重", value=False, key="check_zero")

        with c4:
            net_weight_disp = 0.0
            calc_msg_disp = "請輸入"
            
            scale_val = safe_float(scale_reading_ui)
            
            if scale_val > 0:
                if unit in ["顆", "粒", "錠", "膠囊", "次"]:
                    net_weight_disp = scale_val
                    calc_msg_disp = f"單位: {unit}"
                else:
                    if is_zeroed_ui:
                        net_weight_disp = scale_val
                        calc_msg_disp = "單獨秤重"
                    else:
                        if scale_val < last_ref_weight:
                            calc_msg_disp = "⚠️ 數值異常"
                            net_weight_disp = 0.0
                        else:
                            net_weight_disp = scale_val - last_ref_weight
                            calc_msg_disp = f"扣除前筆 {last_ref_weight}"
            
            if "異常" in calc_msg_disp:
                st.metric("淨重", "---", delta=calc_msg_disp, delta_color="inverse")
            else:
                st.metric("淨重", f"{net_weight_disp:.1f}", delta=calc_msg_disp, delta_color="off")

        btn_disabled = False
        if filter_cat == "請選擇..." or item_name == "請先選類別": btn_disabled = True
        if scale_val <= 0: btn_disabled = True
        if "異常" in calc_msg_disp: btn_disabled = True 

        st.button("⬇️ 加入清單", 
                  type="secondary", 
                  use_container_width=True, 
                  disabled=btn_disabled,
                  on_click=add_to_cart_callback,
                  args=(bowl_weight, last_ref_weight, last_ref_name)
        )

    if st.session_state.cart:
        st.write("##### 🛒 待存清單 (可編輯)")
        df_cart = pd.DataFrame(st.session_state.cart)
        
        edited_df = st.data_editor(
            df_cart,
            use_container_width=True,
            column_config={
                "Item_Name": "品名",
                "Net_Quantity": st.column_config.NumberColumn("數量/淨重", format="%.1f"),
                "Cal_Sub": st.column_config.NumberColumn("熱量", format="%.1f")
            },
            column_order=["Item_Name", "Net_Quantity", "Cal_Sub"],
            num_rows="dynamic",
            key="cart_editor"
        )
        
        if not edited_df.empty:
            try:
                edited_df['Net_Quantity'] = pd.to_numeric(edited_df['Net_Quantity'], errors='coerce').fillna(0)
                edited_df['Cal_Sub'] = pd.to_numeric(edited_df['Cal_Sub'], errors='coerce').fillna(0)
                
                mask_total = ~edited_df['Category'].isin(['藥品', '保養品'])
                live_sum_net = edited_df[mask_total]['Net_Quantity'].sum()
                live_sum_cal = edited_df['Cal_Sub'].sum()
                
                st.info(f"∑ 總計 (不含藥)：{live_sum_net:.1f} g  |  🔥 {live_sum_cal:.1f} kcal")
            except:
                st.caption("計算中...")

        if st.button("💾 儲存寫入 Google Sheet", type="primary", use_container_width=True):
            with st.spinner("寫入中..."):
                rows = []
                str_date = record_date.strftime("%Y/%m/%d")
                str_time = f"{record_time_str}:00"
                timestamp = f"{str_date} {str_time}"

                for i, row_data in edited_df.iterrows():
                    orig_item = next((x for x in st.session_state.cart if x['Item_Name'] == row_data['Item_Name']), {})
                    row = [
                        str(uuid.uuid4()), timestamp, str_date, str_time, meal_name,
                        orig_item.get('ItemID', ''), orig_item.get('Category', ''), 
                        orig_item.get('Scale_Reading', 0), orig_item.get('Bowl_Weight', 0), 
                        row_data['Net_Quantity'], row_data['Cal_Sub'],
                        orig_item.get('Prot_Sub', 0), orig_item.get('Fat_Sub', 0), 
                        orig_item.get('Phos_Sub', 0), "", row_data['Item_Name'], ""
                    ]
                    rows.append(row)
                
                try:
                    sheet_log.append_rows(rows)
                    st.toast("✅ 寫入成功！")
                    st.session_state.cart = []
                    
                    next_index = 0
                    if meal_name in meal_options:
                        curr_idx = meal_options.index(meal_name)
                        if curr_idx < len(meal_options) - 1:
                            next_index = curr_idx + 1
                        else:
                            next_index = curr_idx
                    st.session_state.meal_selector = meal_options[next_index]
                    
                    load_data.clear()
                    st.session_state.just_saved = True
                    st.rerun()
                except Exception as e:
                    st.error(f"寫入失敗：{e}")

# --- 模式 2: 完食 ---
elif nav_mode == "🏁 完食/紀錄剩餘":
    st.markdown(f"##### 🍽️ 編輯：{meal_name}")
    st.caption("紀錄完食時間，若有剩餘，請將剩食倒入新容器(或原碗)秤重")
    
    finish_date = st.date_input("完食日期", value=record_date, key="finish_date_picker")
    str_finish_date = finish_date.strftime("%Y/%m/%d")
    
    default_now = get_tw_time().strftime("%H%M")
    raw_finish_time = st.text_input("完食時間 (如 1806)", value=default_now, key="finish_time_input")
    fmt_finish_time = format_time_str(raw_finish_time)
    
    st.caption(f"📝 將記錄為：{str_finish_date} **{fmt_finish_time}**")

    finish_type = st.radio(
        "狀態", 
        ["全部吃光 (盤光光)", "有剩餘 (需秤重)"], 
        horizontal=True,
        key="finish_radio"
    )
    
    waste_net = 0.0
    waste_cal = 0.0
    
    if finish_type == "有剩餘 (需秤重)":
        st.markdown("---")
        st.caption("請輸入「倒掉時」的秤重數據：")
        
        c_w1, c_w2 = st.columns(2)
        with c_w1:
            waste_gross = st.number_input("1. 容器+剩食 總重 (g)", min_value=0.0, step=0.1, key="waste_gross", value=None, placeholder="輸入總重")
        with c_w2:
            waste_tare = st.number_input("2. 容器空重 (g)", min_value=0.0, step=0.1, key="waste_tare", value=None, placeholder="輸入空重")
        
        val_gross = safe_float(waste_gross)
        val_tare = safe_float(waste_tare)
        waste_net = val_gross - val_tare
        
        if waste_gross is not None and waste_tare is not None:
            if waste_net > 0:
                st.warning(f"📉 實際剩餘淨重：{waste_net:.1f} g")
                if not df_meal.empty:
                    df_meal_clean = clean_duplicate_finish_records(df_meal)
                    meal_foods = df_meal_clean[df_meal_clean['Net_Quantity'].apply(lambda x: safe_float(x)) > 0]
                    
                    exclude_meds = ['藥品', '保養品']
                    if 'Category' in meal_foods.columns:
                        meal_foods['Category'] = meal_foods['Category'].astype(str).str.strip()
                        calc_df = meal_foods[~meal_foods['Category'].isin(exclude_meds)]
                        
                        total_in_cal = calc_df['Cal_Sub'].apply(safe_float).sum()
                        total_in_weight = calc_df['Net_Quantity'].apply(safe_float).sum()
                        
                        if total_in_weight > 0:
                            avg_density = total_in_cal / total_in_weight
                            waste_cal = waste_net * avg_density
                            st.caption(f"預估扣除熱量：{waste_cal:.1f} kcal")
            elif val_gross > 0 and waste_net <= 0:
                st.error("空重不能大於總重！")

    st.button("💾 記錄完食/剩餘", 
              type="primary",
              on_click=save_finish_callback,
              args=(finish_type, waste_net, waste_cal, bowl_weight, meal_name, fmt_finish_time, finish_date)
    )