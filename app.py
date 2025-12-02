# 🚀 Python 程式碼 V4.1 (無提示防跳動版)

iimport streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import uuid

# --- 1. 設定頁面 ---
st.set_page_config(page_title="大文餵食紀錄", page_icon="🐱", layout="wide")

# --- 小工具 ---
def safe_float(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0

def format_time_str(t_str):
    t_str = str(t_str).strip().replace(":", "").replace("：", "")
    if len(t_str) == 3 and t_str.isdigit():
        t_str = "0" + t_str
    if len(t_str) == 4 and t_str.isdigit():
        return f"{t_str[:2]}:{t_str[2:]}"
    return t_str if ":" in str(t_str) else datetime.now().strftime("%H:%M")

# --- 連線設定 (雲端版) ---
@st.cache_resource
def init_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # 改成從 Streamlit 的 Secrets 讀取，而不是讀檔案
    # 注意：這裡的 "gcp_service_account" 要跟您在 Secrets 裡設定的標題一樣
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
#      邏輯函數區 (Callback Functions)
# ==========================================

def add_to_cart_callback(bowl_w, last_ref_w, last_ref_n):
    """
    處理加入清單的邏輯，不回傳任何畫面元素，僅處理數據
    """
    category = st.session_state.get('cat_select', '請選擇...')
    item_name = st.session_state.get('item_select', '請先選類別')
    scale_reading = st.session_state.get('scale_val', 0.0)
    is_zeroed = st.session_state.get('check_zero', False)
    
    if category == "請選擇..." or item_name == "請先選類別" or scale_reading <= 0:
        return

    unit = unit_map.get(item_name, "g")
    
    net_weight = 0.0
    db_scale_reading = scale_reading
    
    if unit in ["顆", "粒", "錠", "膠囊"]:
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

    if unit in ["顆", "粒", "錠", "膠囊"]:
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
    
    # [修正] 移除 st.toast，避免畫面跳動與干擾
    # st.toast(f"✅ 已加入：{item_name} ({net_weight}{unit})")
    
    # 重置輸入框
    st.session_state.scale_val = 0.0
    st.session_state.check_zero = False

# ==========================================
#      UI 佈局開始
# ==========================================
st.title("🐱 大文餵食紀錄")

with st.sidebar:
    st.header("⚙️ 設定")
    record_date = st.date_input("📅 日期", datetime.now())
    str_date_filter = record_date.strftime("%Y/%m/%d")
    
    default_sidebar_time = datetime.now().strftime("%H%M")
    raw_record_time = st.text_input("🕒 時間 (如 0618)", value=default_sidebar_time)
    record_time_str = format_time_str(raw_record_time)
    st.caption(f"將記錄為：{record_time_str}")
    st.caption("輸入數字後，點擊空白處即可生效")

# --- 主畫面區塊 1 ---
recorded_meals = []
df_today = pd.DataFrame()

if not df_log.empty:
    df_today = df_log[df_log['Date'] == str_date_filter].copy()
    if not df_today.empty:
        recorded_meals = df_today['Meal_Name'].unique().tolist()

meal_options = ["第一餐", "第二餐", "第三餐", "第四餐", "第五餐", "點心"]

with st.expander("🥣 餐別與碗重設定 (點擊收合)", expanded=True):
    c_meal, c_bowl = st.columns(2)
    with c_meal:
        def meal_formatter(m):
            return f"{m} (已記)" if m in recorded_meals else m
        meal_name = st.selectbox("🍽️ 餐別", meal_options, format_func=meal_formatter)
    
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
            view_df = df_meal[['Item_Name', 'Net_Quantity', 'Cal_Sub']].copy()
            view_df.columns = ['品名', '數量/重量', '熱量']
            st.dataframe(view_df, use_container_width=True, hide_index=True)

# --- 主畫面區塊 2：數據 ---
day_cal = 0.0
day_weight = 0.0
meal_cal_sum = 0.0
meal_weight_sum = 0.0
supp_str = "無"
med_str = "無"

if not df_today.empty:
    df_today['Cal_Sub'] = pd.to_numeric(df_today['Cal_Sub'], errors='coerce').fillna(0)
    df_today['Net_Quantity'] = pd.to_numeric(df_today['Net_Quantity'], errors='coerce').fillna(0)
    
    mask_day_weight = ~df_today['Category'].isin(['藥品', '保養品', '水'])
    day_weight = df_today[mask_day_weight]['Net_Quantity'].sum()
    day_cal = df_today['Cal_Sub'].sum()

    if not df_meal.empty:
        df_meal['Cal_Sub'] = pd.to_numeric(df_meal['Cal_Sub'], errors='coerce').fillna(0)
        df_meal['Net_Quantity'] = pd.to_numeric(df_meal['Net_Quantity'], errors='coerce').fillna(0)
        mask_meal_weight = ~df_meal['Category'].isin(['藥品', '保養品'])
        meal_weight_sum = df_meal[mask_meal_weight]['Net_Quantity'].sum()
        meal_cal_sum = df_meal['Cal_Sub'].sum()

    if 'Category' in df_today.columns:
        df_supp = df_today[df_today['Category'] == '保養品']
        if not df_supp.empty:
            supp_counts = df_supp.groupby('Item_Name')['Net_Quantity'].sum()
            supp_list = [f"{name}({int(val)})" for name, val in supp_counts.items()]
            supp_str = "、".join(supp_list)
        
        df_med = df_today[df_today['Category'] == '藥品']
        if not df_med.empty:
            med_counts = df_med.groupby('Item_Name')['Net_Quantity'].sum()
            med_list = [f"{name}({int(val)})" for name, val in med_counts.items()]
            med_str = "、".join(med_list)

st.info(
    f"🔥 **本日**: {day_cal:.0f} kcal / {day_weight:.1f} g\n\n"
    f"🍽️ **本餐**: {meal_cal_sum:.0f} kcal / {meal_weight_sum:.1f} g\n\n"
    f"💊 **保養**: {supp_str}\n\n"
    f"💊 **藥品**: {med_str}"
)

# --- 主畫面區塊 3：操作區 ---

if 'cart' not in st.session_state:
    st.session_state.cart = []

last_reading_db = bowl_weight
last_item_db = "碗"
if not df_meal.empty:
    try:
        last_reading_db = float(df_meal.iloc[-1]['Scale_Reading'])
        last_item_db = df_meal.iloc[-1]['Item_Name']
    except:
        pass

if len(st.session_state.cart) > 0:
    last_ref_weight = st.session_state.cart[-1]['Scale_Reading']
    last_ref_name = st.session_state.cart[-1]['Item_Name']
else:
    last_ref_weight = last_reading_db
    last_ref_name = last_item_db

tab1, tab2 = st.tabs(["➕ 新增食物/藥品", "🏁 完食/紀錄剩餘"])

# --- Tab 1: 新增 ---
with tab1:
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            unique_cats = ["請選擇..."] + list(df_items['Category'].unique())
            def on_cat_change(): st.session_state.scale_val = 0.0
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
            if 'scale_val' not in st.session_state: st.session_state.scale_val = 0.0
            
            if unit in ["顆", "粒", "錠", "膠囊"]:
                scale_reading_ui = st.number_input(f"3. 數量 ({unit})", step=1.0, key="scale_val")
                is_zeroed_ui = True 
            else:
                scale_reading_ui = st.number_input("3. 秤重讀數 (g)", step=0.1, format="%.1f", key="scale_val")
                st.caption(f"前筆: {last_ref_weight} g ({last_ref_name})")
                is_zeroed_ui = st.checkbox("⚖️ 已歸零 / 單獨秤重", value=False, key="check_zero")

        with c4:
            net_weight_disp = 0.0
            calc_msg_disp = "請輸入"
            if scale_reading_ui > 0:
                if unit in ["顆", "粒", "錠", "膠囊"]:
                    net_weight_disp = scale_reading_ui
                    calc_msg_disp = f"單位: {unit}"
                else:
                    if is_zeroed_ui:
                        net_weight_disp = scale_reading_ui
                        calc_msg_disp = "單獨秤重"
                    else:
                        if scale_reading_ui < last_ref_weight:
                            calc_msg_disp = "⚠️ 數值異常"
                            net_weight_disp = 0.0
                        else:
                            net_weight_disp = scale_reading_ui - last_ref_weight
                            calc_msg_disp = f"扣除前筆 {last_ref_weight}"
            
            if "異常" in calc_msg_disp:
                st.metric("淨重", "---", delta=calc_msg_disp, delta_color="inverse")
            else:
                st.metric("淨重", f"{net_weight_disp:.1f}", delta=calc_msg_disp, delta_color="off")

        btn_disabled = False
        if filter_cat == "請選擇..." or item_name == "請先選類別": btn_disabled = True
        if scale_reading_ui <= 0: btn_disabled = True
        if "異常" in calc_msg_disp: btn_disabled = True 

        # 使用 callback，移除 st.toast
        st.button("⬇️ 加入清單", 
                  type="secondary", 
                  use_container_width=True, 
                  disabled=btn_disabled,
                  on_click=add_to_cart_callback,
                  args=(bowl_weight, last_ref_weight, last_ref_name)
        )

    if st.session_state.cart:
        st.write("##### 🛒 待存清單")
        df_cart = pd.DataFrame(st.session_state.cart)
        st.dataframe(df_cart[["Item_Name", "Net_Quantity", "Cal_Sub"]], use_container_width=True)
        
        if st.button("💾 儲存寫入 Google Sheet", type="primary", use_container_width=True):
            with st.spinner("寫入中..."):
                rows = []
                str_date = record_date.strftime("%Y/%m/%d")
                str_time = f"{record_time_str}:00"
                timestamp = f"{str_date} {str_time}"

                for item in st.session_state.cart:
                    row = [
                        str(uuid.uuid4()), timestamp, str_date, str_time, meal_name,
                        item['ItemID'], item['Category'], 
                        item['Scale_Reading'], item['Bowl_Weight'], item['Net_Quantity'],
                        item['Cal_Sub'], item['Prot_Sub'], item['Fat_Sub'], item['Phos_Sub'],
                        "", item['Item_Name'], ""
                    ]
                    rows.append(row)
                
                try:
                    sheet_log.append_rows(rows)
                    st.toast("✅ 寫入成功！")
                    st.session_state.cart = []
                    load_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"寫入失敗：{e}")

# --- Tab 2: 完食 ---
with tab2:
    st.info("紀錄完食時間，若有剩餘，請將剩食倒入新容器(或原碗)秤重")
    
    default_now = datetime.now().strftime("%H%M")
    
    c_t1, c_t2 = st.columns(2)
    with c_t1:
        raw_start = st.text_input("開始時間 (如 0639)", value=default_now, key="t_start")
    with c_t2:
        raw_end = st.text_input("結束時間 (如 0700)", value=default_now, key="t_end")
    
    fmt_start = format_time_str(raw_start)
    fmt_end = format_time_str(raw_end)
    finish_time_str = f"{fmt_start} - {fmt_end}"
    
    st.caption(f"📝 將記錄為：**{finish_time_str}**")

    finish_type = st.radio("狀態", ["全部吃光 (盤光光)", "有剩餘 (需秤重)"], horizontal=True)
    
    waste_net = 0.0
    waste_cal = 0.0
    
    if finish_type == "有剩餘 (需秤重)":
        st.markdown("---")
        st.caption("請輸入「倒掉時」的秤重數據：")
        
        c_w1, c_w2 = st.columns(2)
        with c_w1:
            waste_gross = st.number_input("1. 容器+剩食 總重 (g)", min_value=0.0, step=0.1)
        with c_w2:
            waste_tare = st.number_input("2. 容器空重 (g)", min_value=0.0, step=0.1)
        
        waste_net = waste_gross - waste_tare
        
        if waste_gross > 0 or waste_tare > 0:
            if waste_net > 0:
                st.warning(f"📉 實際剩餘淨重：{waste_net:.1f} g")
                if not df_meal.empty:
                    meal_foods = df_meal[df_meal['Net_Quantity'].apply(lambda x: safe_float(x)) > 0]
                    total_in_cal = meal_foods['Cal_Sub'].apply(safe_float).sum()
                    total_in_weight = meal_foods['Net_Quantity'].apply(safe_float).sum()
                    if total_in_weight > 0:
                        avg_density = total_in_cal / total_in_weight
                        waste_cal = waste_net * avg_density
                        st.caption(f"預估扣除熱量：{waste_cal:.1f} kcal")
            elif waste_gross > 0 and waste_net <= 0:
                st.error("空重不能大於總重！")

    if st.button("💾 記錄完食/剩餘", type="primary"):
        if finish_type == "有剩餘 (需秤重)" and waste_net <= 0:
            st.error("剩餘重量計算錯誤，請檢查輸入數值。")
        else:
            str_date = record_date.strftime("%Y/%m/%d")
            str_time_finish = f"{fmt_end}:00"
            timestamp = f"{str_date} {str_time_finish}"
            
            final_waste_net = -waste_net if finish_type == "有剩餘 (需秤重)" else 0
            final_waste_cal = -waste_cal if finish_type == "有剩餘 (需秤重)" else 0
            item_id_code = "WASTE" if finish_type == "有剩餘 (需秤重)" else "FINISH"
            category_code = "剩食" if finish_type == "有剩餘 (需秤重)" else "完食"

            row = [
                str(uuid.uuid4()), timestamp, str_date, str_time_finish, meal_name,
                item_id_code, category_code, 0, bowl_weight, 
                final_waste_net, final_waste_cal, 
                0, 0, 0, "",
                "完食紀錄", finish_time_str
            ]
            try:
                sheet_log.append_row(row)
                st.toast("✅ 完食紀錄已儲存")
                load_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"寫入失敗：{e}")