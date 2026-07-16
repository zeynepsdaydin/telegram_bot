# material_service.py
import os
from openpyxl import load_workbook
from database import log_api_call

EXCEL_FILE = "MUKAYESE RAPORU GENEL.xlsx"

cached_data = None

def load_excel_to_memory():
    """
    Excel dosyasını openpyxl kullanarak RAM'e yükler.
    Pandas bağımlılığını ortadan kaldırır ve C++ derleyicisi gerektirmez.
    """
    global cached_data
    if cached_data is not None:
        return cached_data
        
    if not os.path.exists(EXCEL_FILE):
        print(f"UYARI: {EXCEL_FILE} bulunamadı! Arama servisi çalışmayacak.")
        return None
        
    try:
        print("Excel verileri (openpyxl ile) hafızaya yükleniyor...")
        wb = load_workbook(EXCEL_FILE, read_only=True, data_only=True)
        if 'Sheet1' not in wb.sheetnames:
            print("Hata: Sheet1 bulunamadı.")
            return None
            
        sheet = wb['Sheet1']
        
        # Sizin belgenizin formatına göre:
        # 4. satır (index 4) başlıkları içeriyor (ÜRÜN ADI, BİRİM, MİKTAR, LİNK, SEBEP, BİRİM FİYAT vb.)
        # Veriler ise 5. satırdan (index 5) itibaren başlıyor.
        
        # Başlıkları çekelim
        headers = [cell.value for cell in sheet[4]]
        
        # Kolon indekslerini bulalım
        try:
            prod_idx = headers.index("ÜRÜN ADI")
            unit_idx = headers.index("BİRİM")
            qty_idx = headers.index("MİKTAR")
            link_idx = headers.index("LİNK")
            reason_idx = headers.index("SEBEP")
            # Excel'inizde "BİRİM FİYAT" sütunu HEPSİBURADA altında Unnamed sütunlarda kalabilir. 
            # Güvenli olması için indeks bazlı (8. kolon, yani G/H civarı) veya başlık araması yapıyoruz.
            price_idx = headers.index("BİRİM FİYAT") if "BİRİM FİYAT" in headers else 7 # Varsayılan 8. kolon (0 tabanlı 7)
        except ValueError as ve:
            print(f"Excel başlık eşleştirme hatası: {ve}. Varsayılan indeksler kullanılacak.")
            # Varsayılan indeks atamaları (Excel şablonunuza göre)
            prod_idx, unit_idx, qty_idx, link_idx, reason_idx, price_idx = 2, 3, 4, 5, 6, 7

        temp_data = []
        # 5. satırdan itibaren tüm verileri oku
        for row in sheet.iter_rows(min_row=5, values_only=True):
            if not row or len(row) <= prod_idx or row[prod_idx] is None:
                continue
                
            temp_data.append({
                "urun_adi": str(row[prod_idx]).strip(),
                "birim": str(row[unit_idx]).strip() if row[unit_idx] is not None else "Belirtilmedi",
                "miktar": str(row[qty_idx]).strip() if row[qty_idx] is not None else "Belirtilmedi",
                "link": str(row[link_idx]).strip() if row[link_idx] is not None else "Belirtilmedi",
                "sebep": str(row[reason_idx]).strip() if row[reason_idx] is not None else "Belirtilmedi",
                "hepsiburada_fiyat": str(row[price_idx]).strip() if len(row) > price_idx and row[price_idx] is not None else "Belirtilmedi"
            })
            
        cached_data = temp_data
        print(f"Başarıyla {len(cached_data)} satır malzeme RAM'e yüklendi!")
        return cached_data
    except Exception as e:
        print(f"Excel RAM'e yüklenirken hata oluştu: {e}")
        return None

# Bot başlarken RAM yüklemesini tetikle
load_excel_to_memory()


def search_material_in_report(user_id, query):
    """
    RAM'deki listede arama yapar.
    """
    data = load_excel_to_memory()
    
    if not data:
        error_msg = "Hata: Excel veri tabanı yüklü değil."
        log_api_call(user_id, "search_material", query, error_msg)
        return {"error": error_msg}

    try:
        # Arama terimini içeren malzemeleri filtrele
        match = [item for item in data if query.lower() in item["urun_adi"].lower()]
        
        if not match:
            result_msg = "Aradığınız malzeme mukayese raporunda bulunamadı."
            log_api_call(user_id, "search_material", query, result_msg)
            return {"status": "not_found", "message": result_msg}
        
        # İlk 3 eşleşmeyi al
        results = match[:3]
        log_api_call(user_id, "search_material", query, str(results))
        return {"status": "success", "data": results}

    except Exception as e:
        error_msg = f"Sorgu sırasında hata oluştu: {str(e)}"
        log_api_call(user_id, "search_material", query, error_msg)
        return {"error": error_msg}