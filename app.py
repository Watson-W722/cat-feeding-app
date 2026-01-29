# Python 程式碼 V12.1 (2026 Fix Edition)
# 修正 2026 年 Streamlit API 移除 use_container_width 的問題

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import uuid
import time 

# [V12.0] 新增視覺化套件
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- 1. 設定頁面 ---
st.set_page_config(page_title="大文的飲食日記", page_icon="🐱", layout="wide")

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

def clean_duplicate_finish_records(df):
    if df.empty: return df
    mask_finish = df['ItemID'].isin(['WASTE', 'FINISH'])
    df_others = df[~mask_finish]
    df_finish = df[mask_finish]
    if df_finish.empty: return df
    df_finish_clean = df_finish.drop_duplicates(subset=['Meal_Name'], keep='last')
    return pd.concat([df_others, df_finish_clean], ignore_index=True)

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

# CSS 注入
def inject_custom_css():
    st.markdown("""
    <style>
        :root { 
            --navy: #012172;
            --beige: #BBBF95;
            --bg: #F8FAFC;
            --text-muted: #5A6B8C;
        }
        .stApp { background-color: var(--bg); font-family: 'Segoe UI', sans-serif; color: var(--navy); }
        .stMarkdown, .stRadio label, .stNumberInput label, .stSelectbox label, .stTextInput label, p, h1, h2, h3, h4, h5, h6, span, div {
            color: var(--navy) !important;
        }
        .stNumberInput input, .stTextInput input, .stSelectbox div[data-baseweb="select"] {
            color: var(--navy) !important; background-color: #ffffff !important;
        }
        div[data-testid="stRadio"] label p { color: var(--navy) !important; }
        .block-container { padding-top: 1rem; padding-bottom: 5rem; }
        h4 { font-size: 20px !important; font-weight: 700 !important; color: var(--navy) !important; padding-bottom: 0.5rem; margin-bottom: 0rem; }
        div[data-testid="stVerticalBlock"] > div[style*="background-color"] {
            background: white; border-radius: 16px; box-shadow: 0 2px 6px rgba(0,0,0,0.04); border: 1px solid rgba(1, 33, 114, 0.1); padding: 24px;
        }
        .grid-row-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 12px; }
        .grid-row-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 0px; }
        @media (max-width: 640px) { 
            .grid-row-3 { gap: 6px; } 
            .stat-item { padding: 10px 4px !important; } 
            .stat-value { font-size: 24px !important; } 
            .stat-header { font-size: 12px !important; } 
            div[data-testid="stVerticalBlock"] > div[style*="background-color"] { padding: 16px; }
        }
        .stat-item { background: #fff; border: 2px solid #e2e8f0; border-radius: 12px; padding: 16px 12px; display: flex; flex-direction: column; align-items: center; text-align: center; }
        .stat-header { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; font-size: 14px; font-weight: 700; color: var(--text-muted) !important; text-transform: uppercase; }
        .stat-value { font-size: 32px; font-weight: 900; color: var(--navy) !important; line-height: 1.1; }
        .stat-unit { font-size: 14px; font-weight: 600; color: var(--text-muted) !important; margin-left: 2px; }
        .simple-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0; background: #FDFDF9; border: 1px solid var(--beige); border-radius: 12px; padding: 10px 0; margin-bottom: 15px; width: 100%; }
        .simple-item { text-align: center; padding: 0 2px; border-right: 1px solid rgba(1, 33, 114, 0.1); }
        .simple-item:last-child { border-right: none; }
        .simple-label { font-size: 11px; color: var(--text-muted) !important; font-weight: 700; }
        .simple-value { font-size: 16px; color: var(--navy) !important; font-weight: 800; }
        .simple-unit { font-size: 10px; color: var(--text-muted) !important; margin-left: 1px; }
        .tag-container { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
        .tag { display: inline-flex; align-items: center; padding: 6px 12px; border-radius: 8px; font-size: 14px; font-weight: 600; border: 1px solid transparent; color: var(--navy) !important; }
        .tag-count { background: rgba(255,255,255,0.8); padding: 0px 6px; border-radius: 4px; font-size: 12px; font-weight: 800; margin-left: 6px; color: var(--navy) !important; }
        .bg-orange { background: #fff7ed; color: #f97316; }
        .bg-blue { background: #eff6ff; color: #3b82f6; }
        .bg-cyan { background: #ecfeff; color: #06b6d4; }
        .bg-red { background: #fef2f2; color: #ef4444; }
        .bg-yellow { background: #fefce8; color: #eab308; }
        .tag-green { background: #ecfdf5; border: 1px solid #d1fae5; color: #047857 !important; }
        .tag-red { background: #fff1f2; border: 1px solid #ffe4e6; color: #be123c !important; }
        .main-header { display: flex; align-items: center; gap: 12px; margin-top: 5px; margin-bottom: 24px; padding: 20px; background: white; border-radius: 16px; border: 1px solid rgba(1, 33, 114, 0.1); box-shadow: 0 4px 6px rgba(0,0,0,0.02); }
        .header-icon { background: var(--navy); padding: 12px; border-radius: 12px; color: white !important; display: flex; }
    </style>
    """, unsafe_allow_html=True)

def render_header(date_str):
    cat_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5c.67 0 1.35.09 2 .26 1.78-2 5.03-2.84 6.42-2.26 1.4.58-.42 7-.42 7 .57 1.07 1 2.24 1 3.44C21 17.9 16.97 21 12 21S3 17.9 3 13.44C3 12.24 3.43 11.07 4 10c0 0-1.82-6.42-.42-7 1.39-.58 4.64.26 6.42 2.26.65-.17 1.33-.26 2-.26z"/><path d="M9 13h.01"/><path d="M15 13h.01"/></svg>'
    html = f'<div class="main-header"><div class="header-icon">{cat_svg}</div><div><div style="font-size:24px; font-weight:800; color:#012172;">大文的飲食日記</div><div style="font-size:15px; font-weight:500; color:#5A6B8C;">{date_str}</div></div></div>'
    return html

def render_daily_stats_html(day_stats):
    icons = {
        "flame": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.1.2-2.2.6-3.3a1 1 0 0 0 2.1.7z"></path></svg>',
        "utensils": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/><path d="M7 2v20"/><path d="M21 15V2v0a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"/></svg>',
        "droplets": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 16.3c2.2 0 4-1.83 4-4.05 0-1.16-.57-2.26-1.71-3.19S7.29 6.75 7 5.3c-.29 1.45-1.14 2.84-2.29 3.76S3 11.1 3 12.25c0 2.22 1.8 4.05 4 4.05z"/><path d="M12.56 6.6A10.97 10.97 0 0 0 14 3.02c.5 2.5 2 4.9 4 6.5s3 3.5 3 5.5a6.98 6.98 0 0 1-11.91 4.97"/></svg>',
        "beef": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12.5" cy="8.5" r="2.5"/><path d="M12.5 2a6.5 6.5 0 0 0-6.22 4.6c-1.1 3.13-.78 6.43 1.48 9.17l2.92 2.92c.65.65 1.74.65 2.39 0l.97-.97a6 6 0 0 1 4.24-1.76h.04a6 6 0 0 0 3.79-1.35l.81-.81a2.5 2.5 0 0 0-3.54-3.54l-.47.47a1.5 1.5 0 0 1-2.12 0l-.88-.88a2.5 2.5 0 0 1 0-3.54l.84-.84c.76-.76.88-2 .2-2.86A6.5 6.5 0 0 0 12.5 2Z"/></svg>',
        "dna": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 15c6.638 0 12-5.362 12-12"/><path d="M10 21c6.638 0 12-5.362 12-12"/><path d="m2 3 20 18"/><path d="M12.818 8.182a4.92 4.92 0 0 0-1.636-1.636"/><path d="M16.364 11.728a9.862 9.862 0 0 0-3.092-3.092"/><path d="M9.272 15.364a9.862 9.862 0 0 0-3.092-3.092"/><path d="M12.818 18.91a4.92 4.92 0 0 0-1.636-1.636"/></svg>'
    }
    def get_stat_html(icon, label, value, unit, color_class):
        return f'<div class="stat-item"><div><div class="stat-header"><div class="stat-icon {color_class}">{icons[icon]}</div>{label}</div><div style="display:flex; align-items:baseline; justify-content:center;"><span class="stat-value">{value}</span><span class="stat-unit">{unit}</span></div></div></div>'
    html = '<div class="grid-row-3">' + get_stat_html("flame", "熱量", int(day_stats['cal']), "kcal", "bg-orange") + get_stat_html("utensils", "食物", f"{day_stats['food']:.1f}", "g", "bg-blue") + get_stat_html("droplets", "飲水", f"{day_stats['water']:.1f}", "ml", "bg-cyan") + '</div>'
    html += '<div class="grid-row-2">' + get_stat_html("beef", "蛋白質", f"{day_stats['prot']:.1f}", "g", "bg-red") + get_stat_html("dna", "脂肪", f"{day_stats['fat']:.1f}", "g", "bg-yellow") + '</div>'
    return html

def render_supp_med_html(supp_list, med_list):
    def get_tag_html(items, type_class):
        if not items: return '<span style="color:#5A6B8C; font-size:13px;">無</span>'
        return "".join([f'<span class="tag {type_class}">{item["name"]}<span class="tag-count">x{int(item["count"])}</span></span>' for item in items])
    html = '<div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px;">'
    html += f'<div><div style="display:flex;align-items:center;gap:6px;margin-bottom:8px;font-size:12px;font-weight:700;color:#047857;">保養品</div><div class="tag-container">{get_tag_html(supp_list, "tag-green")}</div></div>'
    html += f'<div style="border-left:1px solid #f1f5f9;padding-left:20px;"><div><div style="display:flex;align-items:center;gap:6px;margin-bottom:8px;font-size:12px;font-weight:700;color:#be123c;">藥品</div><div class="tag-container">{get_tag_html(med_list, "tag-red")}</div></div></div></div>'
    return html

def render_meal_stats_simple(meal_stats):
    html = '<div class="simple-grid">'
    for l, v, u in [("熱量", int(meal_stats['cal']), "kcal"), ("食物", f"{meal_stats['food']:.1f}", "g"), ("飲水", f"{meal_stats['water']:.1f}", "ml"), ("蛋白", f"{meal_stats['prot']:.1f}", "g"), ("脂肪", f"{meal_stats['fat']:.1f}", "g")]:
        html += f'<div class="simple-item"><div class="simple-label">{l}</div><div class="simple-value">{v}<span class="simple-unit">{u}</span></div></div>'
    return html + '</div>'

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

@st.cache_data(ttl=5)
def load_data():
    db_data = sheet_db.get_all_records()
    log_data = sheet_log.get_all_records()
    return pd.DataFrame(db_data), pd.DataFrame(log_data)

df_items, df_log = load_data()

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
#      邏輯函數區
# ==========================================

if 'need_scroll' not in st.session_state: st.session_state.need_scroll = False
if 'range_radio' not in st.session_state: st.session_state.range_radio = "近 7 天"

def on_cat_change():
    st.session_state.scale_val = None
    st.session_state.need_scroll = True

def on_item_change():
    st.session_state.need_scroll = True

def reset_meal_inputs():
    st.session_state.scale_val = None
    st.session_state.check_zero = False
    st.session_state.waste_gross = None
    st.session_state.waste_tare = None
    st.session_state.finish_radio = "全部吃光 (盤光光)"

def get_previous_meal_density(df_log):
    if df_log.empty: return None
    try:
        df_log['Timestamp_dt'] = pd.to_datetime(df_log['Timestamp'], errors='coerce')
        df_waste = df_log[df_log['ItemID'] == 'WASTE'].copy()
        if df_waste.empty: return None
        last_waste = df_waste.sort_values('Timestamp_dt').iloc[-1]
        target_date = last_waste['Date']
        target_meal = last_waste['Meal_Name']
        mask_meal = (df_log['Date'] == target_date) & (df_log['Meal_Name'] == target_meal)
        df_target = df_log[mask_meal].copy()
        exclude_cats = ['藥品', '保養品']
        exclude_items = ['WASTE', 'FINISH']
        for col in ['Net_Quantity', 'Cal_Sub', 'Prot_Sub', 'Fat_Sub', 'Phos_Sub']:
            df_target[col] = pd.to_numeric(df_target[col], errors='coerce').fillna(0)
        mask_valid = (~df_target['Category'].isin(exclude_cats) & ~df_target['ItemID'].isin(exclude_items) & (df_target['Net_Quantity'] > 0))
        df_foods = df_target[mask_valid]
        if df_foods.empty: return None
        total_weight = df_foods['Net_Quantity'].sum()
        if total_weight <= 0: return None
        density = {
            'cal': df_foods['Cal_Sub'].sum() / total_weight,
            'prot': df_foods['Prot_Sub'].sum() / total_weight,
            'fat': df_foods['Fat_Sub'].sum() / total_weight,
            'phos': df_foods['Phos_Sub'].sum() / total_weight,
            'info': f"依據 {target_date} {target_meal}"
        }
        return density
    except: return None

def add_to_cart_callback(bowl_w, last_ref_w, last_ref_n):   
    category = st.session_state.get('cat_select', '請選擇...')
    item_name = st.session_state.get('item_select', '請先選類別')
    raw_scale = st.session_state.get('scale_val')
    scale_reading = safe_float(raw_scale)
    is_zeroed = st.session_state.get('check_zero', False)
    if category == "請選擇..." or item_name == "請先選類別" or scale_reading <= 0: return
    unit = unit_map.get(item_name, "g")
    net_weight = 0.0
    if unit in ["顆", "粒", "錠", "膠囊", "次"]:
        net_weight = scale_reading
        db_scale_reading = last_ref_w  
    else:
        if is_zeroed:
            net_weight = scale_reading
            db_scale_reading = last_ref_w + net_weight 
        else:
            if scale_reading < last_ref_w: return 
            net_weight = scale_reading - last_ref_w
            db_scale_reading = scale_reading
    item_id = item_map.get(item_name, "")
    cat_real = cat_map.get(item_name, "")
    cal_val = safe_float(cal_map.get(item_name, 0))
    prot_val = safe_float(prot_map.get(item_name, 0))
    fat_val = safe_float(fat_map.get(item_name, 0))
    phos_val = safe_float(phos_map.get(item_name, 0))
    if item_id == "LEFTOVER":
        density_data = get_previous_meal_density(df_log)
        if density_data:
            cal_val = density_data['cal'] * 100
            prot_val = density_data['prot'] * 100
            fat_val = density_data['fat'] * 100
            phos_val = density_data['phos'] * 100
            st.toast(f"🔍 已自動代入 {density_data['info']} 的營養密度")
    if unit in ["顆", "粒", "錠", "膠囊", "次"]:
        cal, prot, fat, phos = net_weight*cal_val, net_weight*prot_val, net_weight*fat_val, net_weight*phos_val
    else:
        cal, prot, fat, phos = net_weight*cal_val/100, net_weight*prot_val/100, net_weight*fat_val/100, net_weight*phos_val/100
    current_meal = st.session_state.meal_selector
    st.session_state.cart.append({
        "Category": cat_real, "ItemID": item_id, "Item_Name": item_name,
        "Scale_Reading": db_scale_reading, "Bowl_Weight": bowl_w, "Net_Quantity": net_weight,
        "Cal_Sub": cal, "Prot_Sub": prot, "Fat_Sub": fat, "Phos_Sub": phos, "Unit": unit
    })
    st.session_state.scale_val, st.session_state.check_zero = None, False
    st.session_state.dash_stat_open, st.session_state.dash_med_open, st.session_state.meal_stats_open = False, False, False
    st.session_state.meal_selector = current_meal
    st.session_state.just_added = True 

def lock_meal_state():
    if 'meal_selector' in st.session_state:
        st.session_state.meal_selector = st.session_state.meal_selector

def save_finish_callback(finish_type, waste_net, waste_cal, bowl_w, meal_n, finish_time_str, finish_date_obj, record_date_obj):
    if finish_type == "有剩餘 (需秤重)" and waste_net <= 0:
        st.session_state.finish_error = "剩餘重量計算錯誤"
        return
    str_date_for_db = record_date_obj.strftime("%Y/%m/%d")
    str_finish_date = finish_date_obj.strftime("%Y/%m/%d")
    str_time_finish = f"{finish_time_str}:00"
    timestamp = f"{str_finish_date} {str_time_finish}"
    final_waste_net = -waste_net if finish_type == "有剩餘 (需秤重)" else 0
    final_waste_cal = -waste_cal if finish_type == "有剩餘 (需秤重)" else 0
    item_id_code = "WASTE" if finish_type == "有剩餘 (需秤重)" else "FINISH"
    category_code = "剩食" if finish_type == "有剩餘 (需秤重)" else "完食"
    row = [str(uuid.uuid4()), timestamp, str_date_for_db, str_time_finish, meal_n, item_id_code, category_code, 0, bowl_w, final_waste_net, final_waste_cal, 0, 0, 0, "", "完食紀錄", finish_time_str]
    try:
        current_data = sheet_log.get_all_values()
        header = current_data[0]
        date_idx, meal_idx, item_idx, name_idx = header.index('Date'), header.index('Meal_Name'), header.index('ItemID'), header.index('Item_Name')
        rows_to_delete = [i+1 for i, r in enumerate(current_data[1:], 1) if (r[date_idx] == str_date_for_db and r[meal_idx] == meal_n and r[item_idx] in ['WASTE', 'FINISH'] and len(r) > name_idx and r[name_idx] == "完食紀錄")]
        for r_idx in sorted(rows_to_delete, reverse=True): sheet_log.delete_rows(r_idx)
        sheet_log.append_row(row)
        st.toast("✅ 完食紀錄已更新")
        st.session_state.meal_selector = meal_n
        load_data.clear()
        st.session_state.waste_gross, st.session_state.waste_tare = None, None
        st.session_state.just_saved = True
        st.rerun() 
    except Exception as e: st.session_state.finish_error = f"寫入失敗：{e}"

# ==========================================
#      UI 佈局
# ==========================================

inject_custom_css()

# 初始化狀態
for key in ['dash_stat_open', 'dash_med_open', 'meal_stats_open', 'just_saved', 'just_added', 'finish_radio', 'nav_mode', 'finish_error']:
    if key not in st.session_state: st.session_state[key] = False if 'open' in key or 'just' in key else ("全部吃光 (盤光光)" if key=='finish_radio' else ("➕ 新增食物/藥品" if key=='nav_mode' else None))

# 捲動 JS
scroll_js = """<script>function smoothScroll() { var element = window.parent.document.getElementById("input-anchor"); if (element) element.scrollIntoView({ behavior: 'smooth', block: 'start' }); } setTimeout(smoothScroll, 500);</script>"""
if st.session_state.just_saved or st.session_state.just_added or st.session_state.get('need_scroll', False):
    components.html(scroll_js, height=0)
    st.session_state.just_saved = st.session_state.just_added = st.session_state.need_scroll = False

with st.sidebar:
    st.header("⚙️ 設定")
    tw_now = get_tw_time()
    record_date = st.date_input("📅 日期", tw_now)
    str_date_filter = record_date.strftime("%Y/%m/%d")
    raw_record_time = st.text_input("🕒 時間 (如 0618)", value=tw_now.strftime("%H%M"))
    record_time_str = format_time_str(raw_record_time)
    if st.button("🔄 重新整理數據"): load_data.clear(); st.rerun()

df_today, day_stats, meal_stats, supp_list, med_list = pd.DataFrame(), {'cal':0, 'food':0, 'water':0, 'prot':0, 'fat':0}, {'name': '尚未選擇', 'cal':0, 'food':0, 'water':0, 'prot':0, 'fat':0}, [], []
if not df_log.empty:
    df_today = df_log[df_log['Date'] == str_date_filter].copy()
    if not df_today.empty:
        df_today['Category'] = df_today['Category'].astype(str).str.strip()
        for col in ['Cal_Sub', 'Net_Quantity', 'Prot_Sub', 'Fat_Sub']: df_today[col] = pd.to_numeric(df_today[col], errors='coerce').fillna(0)
        df_today = clean_duplicate_finish_records(df_today)
        f_net, w_net = calculate_intake_breakdown(df_today)
        day_stats.update({'cal': df_today['Cal_Sub'].sum(), 'food': f_net, 'water': w_net, 'prot': df_today['Prot_Sub'].sum(), 'fat': df_today['Fat_Sub'].sum()})
        df_supp = df_today[df_today['Category'] == '保養品']
        if not df_supp.empty: supp_list = [{'name': k, 'count': v} for k, v in df_supp.groupby('Item_Name')['Net_Quantity'].sum().items()]
        df_med = df_today[df_today['Category'] == '藥品']
        if not df_med.empty: med_list = [{'name': k, 'count': v} for k, v in df_med.groupby('Item_Name')['Net_Quantity'].sum().items()]

st.markdown(render_header(record_date.strftime("%Y年 %m月 %d日")), unsafe_allow_html=True)
col_dash, col_input = st.columns([4, 3], gap="medium")

with col_dash:
    with st.container(border=True):
        st.markdown("#### 📊 本日健康總覽")
        with st.expander("📈 飲食趨勢分析", expanded=False):
            range_option = st.radio("區間", ["近 7 天", "近 30 天", "近 90 天", "自訂"], horizontal=True, label_visibility="collapsed", key="range_radio")
            today_date = get_tw_time().date()
            d_start = today_date - timedelta(days=6 if range_option=="近 7 天" else (29 if range_option=="近 30 天" else 89))
            date_range_val = st.date_input("選擇區間", value=(d_start, today_date), max_value=today_date)
            if isinstance(date_range_val, tuple) and len(date_range_val) == 2:
                start_date, end_date = date_range_val
                temp_dt = pd.to_datetime(df_log['Date'], format='%Y/%m/%d', errors='coerce')
                df_valid = df_log[temp_dt.notna()].copy(); df_valid['Date_dt'] = temp_dt[temp_dt.notna()].dt.date
                df_trend = clean_duplicate_finish_records(df_valid[(df_valid['Date_dt'] >= start_date) & (df_valid['Date_dt'] <= end_date)])
                if not df_trend.empty:
                    trend_data = []
                    for d, group in df_trend.groupby('Date_dt'):
                        f, w = calculate_intake_breakdown(group)
                        trend_data.append({'Date': d, 'Calorie': group['Cal_Sub'].sum(), 'Food_g': f, 'Water_ml': w})
                    df_chart = pd.DataFrame(trend_data).sort_values('Date')
                    for c in ['Cal', 'Water', 'Food']: df_chart[f'{c}_MA7'] = df_chart['Calorie' if c=='Cal' else f'{c}_g' if c=='Food' else 'Water_ml'].rolling(window=7, min_periods=1).mean()
                    fig = make_subplots(specs=[[{"secondary_y": True}]])
                    fig.add_trace(go.Bar(x=df_chart['Date'], y=df_chart['Calorie'], name="熱量", marker_color='#FFD700', opacity=0.6, offsetgroup=0), secondary_y=False)
                    fig.add_trace(go.Bar(x=df_chart['Date'], y=df_chart['Food_g'], name="食量", marker_color='#90EE90', opacity=0.6, offsetgroup=1), secondary_y=False)
                    fig.add_trace(go.Scatter(x=df_chart['Date'], y=df_chart['Water_ml'], name="飲水", line=dict(color='#00BFFF', width=1, dash='dot')), secondary_y=True)
                    fig.update_layout(height=500, legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5), margin=dict(l=20, r=20, t=20, b=100), hovermode="x unified", barmode='group')
                    st.markdown(f"##### 📊 飲食趨勢 ({start_date.strftime('%m/%d')} - {end_date.strftime('%m/%d')})")
                    # [2026 Fix] use_container_width=True -> width="stretch"
                    st.plotly_chart(fig, width="stretch")
        with st.expander("📝 今日營養攝取", expanded=st.session_state.dash_stat_open): st.markdown(render_daily_stats_html(day_stats), unsafe_allow_html=True)
        with st.expander("💊 今日保養與藥品", expanded=st.session_state.dash_med_open): st.markdown(render_supp_med_html(supp_list, med_list), unsafe_allow_html=True)

with col_input:
    meal_options = ["第一餐", "第二餐", "第三餐", "第四餐", "第五餐", "第六餐", "第七餐", "第八餐", "第九餐", "第十餐", "點心1", "點心2"]
    meal_status_map = {m: " (已記)" for m in (df_today['Meal_Name'].unique() if not df_today.empty else [])}
    if not df_today.empty:
        for _, row in df_today[df_today['ItemID'].isin(['FINISH', 'WASTE'])].iterrows(): meal_status_map[row['Meal_Name']] = f" (已記) (完食: {str(row['Time'])[:5]})"
    if 'meal_selector' not in st.session_state:
        st.session_state.meal_selector = next((m for m in meal_options if m not in (df_today['Meal_Name'].unique() if not df_today.empty else [])), meal_options[0])
    
    with st.container(border=True):
        st.markdown("#### 🍽️ 飲食紀錄")
        c_meal, c_bowl = st.columns(2)
        meal_name = c_meal.selectbox("餐別", meal_options, format_func=lambda m: f"{m}{meal_status_map.get(m, '')}", key="meal_selector", on_change=reset_meal_inputs)
        df_meal = df_today[df_today['Meal_Name'] == meal_name] if not df_today.empty else pd.DataFrame()
        bowl_weight = c_bowl.number_input("🥣 碗重 (g)", value=float(df_meal.iloc[-1]['Bowl_Weight']) if not df_meal.empty else 30.0, step=0.1, format="%.1f")
        if not df_meal.empty:
            with st.expander(f"📜 {meal_name} 明細"):
                view_df = df_meal[['Item_Name', 'Net_Quantity', 'Cal_Sub', 'Time']].copy()
                view_df['Item_Name'] = view_df.apply(lambda r: f"{r['Item_Name']} {str(r['Time'])[:5]}" if '完食' in str(r['Item_Name']) else r['Item_Name'], axis=1)
                # [2026 Fix] use_container_width=True -> width="stretch"
                st.dataframe(view_df.drop(columns=['Time']), width="stretch", hide_index=True)
        meal_stats.update({'name': meal_name})
        if not df_meal.empty:
            df_m_c = clean_duplicate_finish_records(df_meal)
            fm, wm = calculate_intake_breakdown(df_m_c)
            meal_stats.update({'food': fm, 'water': wm, 'cal': df_m_c['Cal_Sub'].sum(), 'prot': df_m_c['Prot_Sub'].sum(), 'fat': df_m_c['Fat_Sub'].sum()})
        with st.expander("📊 本餐小計", expanded=st.session_state.meal_stats_open): st.markdown(render_meal_stats_simple(meal_stats), unsafe_allow_html=True)
        st.divider()
        st.markdown('<div id="input-anchor" style="height:0px; margin-top:-10px;"></div>', unsafe_allow_html=True)
        nav_mode = st.radio("模式", ["➕ 新增食物/藥品", "🏁 完食/紀錄剩餘"], horizontal=True, label_visibility="collapsed", key="nav_mode")
        if 'cart' not in st.session_state: st.session_state.cart = []
        last_ref_w = st.session_state.cart[-1]['Scale_Reading'] if st.session_state.cart else (float(df_meal[~df_meal['ItemID'].isin(['WASTE', 'FINISH'])].iloc[-1]['Scale_Reading']) if not df_meal.empty and not df_meal[~df_meal['ItemID'].isin(['WASTE', 'FINISH'])].empty else bowl_weight)
        last_ref_n = st.session_state.cart[-1]['Item_Name'] if st.session_state.cart else (df_meal[~df_meal['ItemID'].isin(['WASTE', 'FINISH'])].iloc[-1]['Item_Name'] if not df_meal.empty and not df_meal[~df_meal['ItemID'].isin(['WASTE', 'FINISH'])].empty else "碗")

        if nav_mode == "➕ 新增食物/藥品":
            with st.container(border=True):
                c1, c2 = st.columns(2)
                f_cat = c1.selectbox("1. 類別", ["請選擇..."] + list(df_items['Category'].unique()), key="cat_select", on_change=on_cat_change)
                i_name = c2.selectbox("2. 品名", df_items[df_items['Category'] == f_cat]['Item_Name'].tolist() if f_cat != "請選擇..." else ["請先選類別"], key="item_select", on_change=on_item_change)
                unit = unit_map.get(i_name, "g")
                c3, c4 = st.columns(2)
                sc_ui = c3.number_input(f"3. 讀數 ({unit})" if unit != "g" else "3. 秤重讀數 (g)", step=1.0 if unit != "g" else 0.1, format=None if unit != "g" else "%.1f", key="scale_val", value=None, placeholder="輸入")
                is_z = c3.checkbox("⚖️ 已歸零 / 單獨秤重", value=False, key="check_zero") if unit == "g" else True
                sc_val = safe_float(sc_ui)
                nw, msg = (sc_val, f"單位: {unit}") if unit != "g" else ((sc_val, "單獨秤重") if is_z else ((0.0, "⚠️ 異常") if sc_val < last_ref_w else (sc_val - last_ref_w, f"扣除前筆 {last_ref_w}")))
                c4.metric("淨重", f"{nw:.1f}", delta=msg, delta_color="inverse" if "異常" in msg else "off")
                # [2026 Fix] use_container_width=True -> width="stretch"
                st.button("⬇️ 加入清單", type="secondary", width="stretch", disabled=(f_cat=="請選擇..." or i_name=="請先選類別" or sc_val<=0 or "異常" in msg), on_click=add_to_cart_callback, args=(bowl_weight, last_ref_w, last_ref_n))
            if st.session_state.cart:
                # [2026 Fix] use_container_width=True -> width="stretch"
                ed_df = st.data_editor(pd.DataFrame(st.session_state.cart), width="stretch", column_config={"Item_Name": "品名", "Net_Quantity": st.column_config.NumberColumn("淨重", format="%.1f"), "Cal_Sub": st.column_config.NumberColumn("熱量", format="%.1f")}, column_order=["Item_Name", "Net_Quantity", "Cal_Sub"], num_rows="fixed", key="cart_editor").dropna(subset=['Item_Name'])
                if not ed_df.empty:
                    f_sum = ed_df[~ed_df['Category'].isin(['藥品', '保養品'])]['Net_Quantity'].sum() if 'Category' in ed_df.columns else ed_df['Net_Quantity'].sum()
                    st.info(f"∑ 總計 (不含藥)：{f_sum:.1f} g | 🔥 {ed_df['Cal_Sub'].sum():.1f} kcal")
                del_i = st.selectbox("🗑️ 刪除", ["請選擇..."] + [f"{i+1}. {r['Item_Name']}({r['Net_Quantity']}g)" for i, r in ed_df.iterrows()])
                if del_i != "請選擇..." and st.button("確認刪除"): st.session_state.cart.pop(int(del_i.split(".")[0])-1); st.rerun()
                # [2026 Fix] use_container_width=True -> width="stretch"
                if st.button("💾 儲存寫入 Google Sheet", type="primary", width="stretch", on_click=lock_meal_state):
                    rows = [[str(uuid.uuid4()), f"{str_date_filter} {record_time_str}:00", str_date_filter, f"{record_time_str}:00", meal_name, r.get('ItemID',''), r.get('Category',''), r.get('Scale_Reading',0), r.get('Bowl_Weight',0), safe_float(r['Net_Quantity']), safe_float(r['Cal_Sub']), r.get('Prot_Sub',0), r.get('Fat_Sub',0), r.get('Phos_Sub',0), "", r['Item_Name'], ""] for _, r in ed_df.iterrows()]
                    try: sheet_log.append_rows(rows); st.toast("✅ 寫入成功"); st.session_state.cart, st.session_state.just_saved = [], True; load_data.clear(); st.rerun()
                    except Exception as e: st.error(f"錯誤：{e}")

        elif nav_mode == "🏁 完食/紀錄剩餘":
            f_date = st.date_input("完食日期", value=record_date); f_time = format_time_str(st.text_input("完食時間", value=get_tw_time().strftime("%H%M")))
            f_type = st.radio("狀態", ["全部吃光 (盤光光)", "有剩餘 (需秤重)"], horizontal=True, key="finish_radio")
            wn, wc = 0.0, 0.0
            if f_type == "有剩餘 (需秤重)":
                cw1, cw2 = st.columns(2)
                vg, vt = safe_float(cw1.number_input("總重", value=None)), safe_float(cw2.number_input("容器重", value=None))
                wn = vg - vt
                if wn > 0 and not df_meal.empty:
                    calc_df = df_meal[~df_meal['Category'].isin(['藥品', '保養品']) & (df_meal['Net_Quantity'] > 0)]
                    if not calc_df.empty: wc = wn * (calc_df['Cal_Sub'].sum() / calc_df['Net_Quantity'].sum()); st.warning(f"📉 剩餘：{wn:.1f}g (約扣除 {wc:.1f}kcal)")
            st.button("💾 記錄完食", type="primary", on_click=save_finish_callback, args=(f_type, wn, wc, bowl_weight, meal_name, f_time, f_date, record_date))