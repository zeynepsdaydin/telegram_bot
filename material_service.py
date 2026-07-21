# material_service.py
import os
from openpyxl import load_workbook
from database import log_api_call

EXCEL_FILE = "MUKAYESE RAPORU GENEL.xlsx"

cached_data = None

def load_excel_to_memory():
    global cached_data
    if cached_data is not None:
        return cached_data
        
    if not os.path.exists(EXCEL_FILE):
        print(f"UYARI: {EXCEL_FILE} bulunamadı! Arama servisi çalışmayacak.")
        return None
        
    try:
        print("Excel verileri (Garantili İndeks Eşleşmesi) hafızaya yükleniyor...")
        # read_only=False yaparak indeks kaymalarının önüne geçiyoruz
        wb = load_workbook(EXCEL_FILE, read_only=False, data_only=True)
        if 'Sheet1' not in wb.sheetnames:
            print("Hata: Sheet1 bulunamadı.")
            return None
            
        sheet = wb['Sheet1']
        
        # Tüm satırları bir listeye alalım ki indeksler %100 senkronize olsun
        all_rows = list(sheet.iter_rows(values_only=True))
        
        # 3. ve 4. satırları (0 tabanlı 2 ve 3) çekelim
        row_3 = all_rows[2]  # Firma adları
        row_4 = all_rows[3]  # "ÜRÜN ADI", "BİRİM FİYAT" başlıkları
        
        # Temel sütun indekslerini bulalım
        prod_idx, unit_idx, qty_idx, link_idx, reason_idx = 2, 3, 4, 5, 6
        for idx, cell in enumerate(row_4):
            if cell:
                cell_upper = str(cell).upper().replace("İ", "I").strip()
                if "URUN ADI" in cell_upper: 
                    prod_idx = idx
                elif "BIRIM" in cell_upper and "FIYAT" not in cell_upper: 
                    unit_idx = idx
                elif "MIKTAR" in cell_upper: 
                    qty_idx = idx
                elif "LINK" in cell_upper: 
                    link_idx = idx
                elif "SEBEP" in cell_upper: 
                    reason_idx = idx

        # Fiyat sütunlarını ve ait oldukları firmaları belirleyelim
        price_columns = {}
        for idx, cell in enumerate(row_4):
            if cell:
                cell_upper = str(cell).upper().replace("İ", "I").strip()
                if "BIRIM FIYAT" in cell_upper or "FIYAT" in cell_upper:
                    # En yakın geçerli firma adını bulmak için sola doğru tara
                    firma_adi = "Belirtilmeyen Firma"
                    for look_back in range(idx, -1, -1):
                        if look_back < len(row_3) and row_3[look_back] is not None:
                            firma_adi = str(row_3[look_back]).strip()
                            break
                    price_columns[idx] = firma_adi

        temp_data = []
        # 5. satırdan (index 4) itibaren verileri oku
        for row in all_rows[4:]:
            if not row or len(row) <= prod_idx or row[prod_idx] is None:
                continue
                
            fiyat_teklifleri = []
            for col_idx, f_name in price_columns.items():
                if col_idx < len(row) and row[col_idx] is not None:
                    val = str(row[col_idx]).strip()
                    if val and val.lower() != "none" and val != "0" and val != "0.0":
                        if not val.endswith("TL"):
                            val = f"{val} TL"
                        fiyat_teklifleri.append(f"{f_name}: {val}")
            
            fiyat_ozeti = ", ".join(fiyat_teklifleri) if fiyat_teklifleri else "Fiyat belirtilmedi"

            temp_data.append({
                "urun_adi": str(row[prod_idx]).strip(),
                "birim": str(row[unit_idx]).strip() if row[unit_idx] is not None else "Belirtilmedi",
                "miktar": str(row[qty_idx]).strip() if row[qty_idx] is not None else "Belirtilmedi",
                "link": str(row[link_idx]).strip() if row[link_idx] is not None else "Belirtilmedi",
                "sebep": str(row[reason_idx]).strip() if row[reason_idx] is not None else "Belirtilmedi",
                "fiyat_listesi": fiyat_ozeti
            })
            
        cached_data = temp_data
        print(f"Başarıyla {len(cached_data)} satır malzeme RAM'e yüklendi!")
        return cached_data
    except Exception as e:
        print(f"Excel RAM'e yüklenirken hata oluştu: {e}")
        return None

load_excel_to_memory()

def search_material_in_report(user_id, query):
    data = load_excel_to_memory()
    if not data:
        error_msg = "Hata: Excel veri tabanı yüklü değil."
        log_api_call(user_id, "search_material", query, error_msg)
        return {"error": error_msg}

    try:
        match = [item for item in data if query.lower() in item["urun_adi"].lower()]
        if not match:
            result_msg = "Aradığınız malzeme mukayese raporunda bulunamadı."
            log_api_call(user_id, "search_material", query, result_msg)
            return {"status": "not_found", "message": result_msg}
        
        results = match[:3]
        log_api_call(user_id, "search_material", query, str(results))
        return {"status": "success", "data": results}
    except Exception as e:
        error_msg = f"Sorgu sırasında hata oluştu: {str(e)}"
        log_api_call(user_id, "search_material", query, error_msg)
        return {"error": error_msg}