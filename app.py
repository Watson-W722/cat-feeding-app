# Python 程式碼 V3.3 (RWD 與邏輯優化版)

import streamlit as st
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
#      UI 佈局開始
# ==========================================
st.title("🐱 大文餵食紀錄")

# --- 側邊欄：只放日期時間 (較少變動) ---
with st.sidebar:
    st.header("⚙️ 日期設定")
    record_date = st.date_input("📅 日期", datetime.now())
    str_date_filter = record_date.strftime("%Y/%m/%d")
    record_time = st.time_input("🕒 時間", datetime.now())
    st.caption("餐別與碗重請在主畫面設定")

# ==========================================
#      主畫面區塊 1：餐別與碗重 (RWD 優化)
# ==========================================
# 將這塊移出 Sidebar，放在主畫面頂部，方便手機操作
# 使用 expander 預設展開，填完可收起
with st.expander("🥣 餐別與碗重設定 (點擊收合)", expanded=True):
    c_meal, c_bowl = st.columns(2)
    with c_meal:
        meal_name = st.selectbox("🍽️ 餐別", ["第一餐", "第二餐", "第三餐", "第四餐", "第五餐", "點心"])
    
    # 自動抓碗重邏輯
    last_bowl = 30.0
    if not df_log.empty:
        mask = (df_log['Date'] == str_date_filter) & (df_log['Meal_Name'] == meal_name)
        today_meal_log = df_log[mask]
        if not today_meal_log.empty:
            try:
                last_bowl = float(today_meal_log.iloc[-1]['Bowl_Weight'])
            except:
                pass
    
    with c_bowl:
        bowl_weight = st.number_input("🥣 碗重 (g)", value=last_bowl, step=0.1)

# ==========================================
#      主畫面區塊 2：數據儀表板
# ==========================================
# 簡單顯示當日統計，不佔太多空間
if not df_log.empty:
    df_today = df_log[df_log['Date'] == str_date_filter].copy()
    if not df_today.empty:
        df_today['Cal_Sub'] = pd.to_numeric(df_today['Cal_Sub'], errors='coerce').fillna(0)
        day_calories = df_today['Cal_Sub'].sum()
        
        # 顯示本餐已攝取 (方便補登參考)
        mask_meal = (df_today['Meal_Name'] == meal_name)
        df_meal = df_today[mask_meal]
        meal_cal = pd.to_numeric(df_meal['Cal_Sub'], errors='coerce').sum()
        
        # 抓上一筆秤重 (補登參考用)
        try:
            last_reading_db = float(df_meal.iloc[-1]['Scale_Reading'])
            last_item_db = df_meal.iloc[-1]['Item_Name']
        except:
            last_reading_db = bowl_weight
            last_item_db = "碗"
    else:
        day_calories = 0
        meal_cal = 0
        last_reading_db = bowl_weight
        last_item_db = "碗"
else:
    day_calories = 0
    meal_cal = 0
    last_reading_db = bowl_weight
    last_item_db = "碗"

st.info(f"🔥 本日熱量: {day_calories:.0f} kcal | 🍽️ 本餐熱量: {meal_cal:.0f} kcal")

# ==========================================
#      主畫面區塊 3：操作區 (Tabs)
# ==========================================

if 'cart' not in st.session_state:
    st.session_state.cart = []

# 決定上一筆參考重量 (優先看購物車 -> 再看資料庫)
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
        # 類別與品名 (2欄)
        c1, c2 = st.columns(2)
        with c1:
            unique_cats = ["請選擇..."] + list(df_items['Category'].unique())
            filter_cat = st.selectbox("1. 類別", unique_cats)
            
            if filter_cat == "請選擇..." or filter_cat == "全部":
                filtered_items = []
                if filter_cat == "全部": filtered_items = df_items['Item_Name'].tolist()
            else:
                filtered_items = df_items[df_items['Category'] == filter_cat]['Item_Name'].tolist()

        with c2:
            item_name = st.selectbox("2. 品名", filtered_items if filtered_items else ["請先選類別"])

        unit = unit_map.get(item_name, "g")
        
        # 秤重與邏輯 (2欄)
        c3, c4 = st.columns(2)
        
        with c3:
            if unit in ["顆", "粒", "錠", "膠囊"]:
                scale_reading = st.number_input(f"3. 數量 ({unit})", value=0.0, step=1.0)
                # 顆數模式：強制為獨立
                is_zeroed = True 
                db_scale_reading = last_ref_weight # 顆數不改變秤重讀數
            else:
                # 重量模式 (g, ml)
                scale_reading = st.number_input("3. 秤重讀數 (g)", value=0.0, step=0.1)
                db_scale_reading = scale_reading
                
                # --- [關鍵修改] 歸零勾選框常駐 ---
                # 讓使用者可以隨時決定這筆是不是歸零後的
                st.caption(f"上一筆讀數: {last_ref_weight} g ({last_ref_name})")
                is_zeroed = st.checkbox("⚖️ 已歸零 / 單獨秤重", value=False)

        with c4:
            # 計算邏輯
            net_weight = 0.0
            calc_msg = "請輸入"
            
            if scale_reading > 0:
                if unit in ["顆", "粒", "錠", "膠囊"]:
                    net_weight = scale_reading
                    calc_msg = f"單位: {unit}"
                else:
                    if is_zeroed:
                        # 勾選歸零 -> 淨重 = 輸入值
                        net_weight = scale_reading
                        calc_msg = "單獨秤重"
                    else:
                        # 未勾選 -> 累加模式
                        if scale_reading < last_ref_weight:
                            calc_msg = "⚠️ 數值異常 (小於前筆)"
                            net_weight = 0.0
                        else:
                            net_weight = scale_reading - last_ref_weight
                            calc_msg = f"扣除前筆 {last_ref_weight}"
            
            # 顯示大數字
            if "異常" in calc_msg:
                st.metric("淨重", "---", delta=calc_msg, delta_color="inverse")
            else:
                st.metric("淨重", f"{net_weight:.1f}", delta=calc_msg, delta_color="off")

        # 加入按鈕
        btn_disabled = False
        if filter_cat == "請選擇..." or item_name == "請先選類別": btn_disabled = True
        if scale_reading <= 0: btn_disabled = True
        if "異常" in calc_msg: btn_disabled = True # 異常時鎖住

        if st.button("⬇️ 加入清單", type="secondary", use_container_width=True, disabled=btn_disabled):
            # 準備資料
            item_id = item_map.get(item_name, "")
            category = cat_map.get(item_name, "")
            
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
                "Category": category,
                "ItemID": item_id,
                "Item_Name": item_name,
                "Scale_Reading": db_scale_reading,
                "Bowl_Weight": bowl_weight,
                "Net_Quantity": net_weight,
                "Cal_Sub": cal,
                "Prot_Sub": prot,
                "Fat_Sub": fat,
                "Phos_Sub": phos,
                "Unit": unit
            })
            st.success(f"已加入：{item_name}")
            st.rerun()

    # 顯示購物車
    if st.session_state.cart:
        st.write("##### 🛒 待存清單")
        df_cart = pd.DataFrame(st.session_state.cart)
        st.dataframe(df_cart[["Item_Name", "Net_Quantity", "Cal_Sub"]], use_container_width=True)
        
        if st.button("💾 儲存寫入 Google Sheet", type="primary", use_container_width=True):
            with st.spinner("寫入中..."):
                rows = []
                str_date = record_date.strftime("%Y/%m/%d")
                now_time = datetime.now().strftime("%H:%M:%S")
                timestamp = f"{str_date} {now_time}"

                for item in st.session_state.cart:
                    row = [
                        str(uuid.uuid4()), timestamp, str_date, now_time, meal_name,
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
    st.info("在此記錄完食時間，或扣除剩餘重量")
    
    # [修正邏輯] 計算應有總重 (碗 + 食物)
    if not df_log.empty:
        mask_m = (df_log['Date'] == str_date_filter) & (df_log['Meal_Name'] == meal_name)
        df_m = df_log[mask_m]
        # 只算食物 (排除剩食紀錄)
        df_m_food = df_m[df_m['Net_Quantity'].apply(lambda x: safe_float(x)) > 0]
        total_net_in_db = df_m_food['Net_Quantity'].apply(safe_float).sum()
    else:
        total_net_in_db = 0
    
    expected_total_scale = bowl_weight + total_net_in_db
    
    # 顯示提示資訊
    c_info1, c_info2 = st.columns(2)
    c_info1.metric("🥣 碗重", f"{bowl_weight} g")
    c_info2.metric("📦 應有總重 (含碗)", f"{expected_total_scale:.1f} g", help="碗重 + 本餐已加入的所有食物")

    st.divider()

    with st.form("finish_form"):
        default_time_str = datetime.now().strftime("%H:%M")
        finish_time_str = st.text_input("完食時間 (如 12:00-12:30)", value=default_time_str)
        finish_type = st.radio("狀態", ["全部吃光 (盤光光)", "有剩餘 (需秤重)"], horizontal=True)
        
        waste_net = 0.0
        waste_cal = 0.0
        
        if finish_type == "有剩餘 (需秤重)":
            final_scale = st.number_input("剩餘含碗總重 (g)", min_value=0.0, step=0.1)
            
            # [修正邏輯] 剩餘淨重 = 最後秤重 - 碗重
            if final_scale > 0:
                waste_net = final_scale - bowl_weight
                st.warning(f"剩餘淨重：{waste_net:.1f} g")
                
                # 計算扣除熱量 (加權平均)
                if total_net_in_db > 0:
                    total_cal_in_db = df_m_food['Cal_Sub'].apply(safe_float).sum()
                    avg_density = total_cal_in_db / total_net_in_db
                    waste_cal = waste_net * avg_density
                    st.caption(f"預估扣除熱量：{waste_cal:.1f} kcal")

        submitted = st.form_submit_button("💾 記錄完食/剩餘", type="primary")
        
        if submitted:
            str_date = record_date.strftime("%Y/%m/%d")
            now_time = datetime.now().strftime("%H:%M:%S")
            timestamp = f"{str_date} {now_time}"
            
            row = [
                str(uuid.uuid4()), timestamp, str_date, now_time, meal_name,
                "WASTE" if waste_net > 0 else "FINISH",
                "剩食", 0, bowl_weight, -waste_net, -waste_cal, 0, 0, 0, "",
                "完食紀錄", finish_time_str
            ]
            try:
                sheet_log.append_row(row)
                st.toast("✅ 完食紀錄已儲存")
                load_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"寫入失敗：{e}")