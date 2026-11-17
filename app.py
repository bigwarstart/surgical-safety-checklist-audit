# -*- coding: utf-8 -*-
"""
HBYS rapor sunucusu: küçük, bağımsız bir Flask uygulaması.

Raporların kendisi (menü, açıklama, SQL, kolonlar) raporlar.py dosyasındadır.
Uygulama veritabanına SADECE okuma (SELECT) yapar.

Demo modu: veritabanı olmadan, uydurma verilerle denemek için
    DEMO=1 python app.py        (Windows: set DEMO=1 && python app.py)
"""
import configparser
import io
import ipaddress
import logging
import os
import re
import secrets
from datetime import datetime, timedelta

from flask import Flask, Response, jsonify, render_template, request, send_file
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import raporlar

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.ini")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("hbys-rapor")

cfg = configparser.RawConfigParser()  # şifrede % gibi karakterler sorun çıkarmasın
cfg.read(CONFIG_PATH, encoding="utf-8")
for _bolum in ("veritabani", "uygulama", "guvenlik"):
    if not cfg.has_section(_bolum):
        cfg.add_section(_bolum)

DB = cfg["veritabani"]
APP = cfg["uygulama"]
GUV = cfg["guvenlik"]
DEMO = os.environ.get("DEMO") == "1" or APP.get("demo", "").strip().lower() in ("1", "true", "evet")
HASTANE_NO = int(APP.get("hastane_no", "1"))

if not DEMO and not DB.get("sunucu"):
    raise SystemExit("config.ini bulunamadı ya da eksik. config.ini.ornek dosyasını kopyalayıp "
                     "config.ini yapın ve doldurun. (Veritabanısız denemek için: DEMO=1)")

app = Flask(__name__)
_pool = None


# ----------------------------------------------------------------------------
# ERİŞİM KONTROLÜ
# Raporlarda hasta adı gibi kişisel veriler bulunur (KVKK). Bu yüzden iki
# isteğe bağlı koruma vardır (config.ini > [guvenlik]):
#   izinli_ag  : yalnızca bu ağlardan gelen istekler kabul edilir
#                (ör. 192.168.10.0/24, 192.168.20.15/32 — virgülle ayırın)
#   kullanici / sifre : tarayıcı kullanıcı adı ve şifre sorar (HTTP Basic)
# ----------------------------------------------------------------------------
IZINLI_AGLAR = [ipaddress.ip_network(a.strip(), strict=False)
                for a in GUV.get("izinli_ag", "").split(",") if a.strip()]
GIRIS_KULLANICI = GUV.get("kullanici", "").strip()
GIRIS_SIFRE = GUV.get("sifre", "")


@app.before_request
def erisim_kontrolu():
    if IZINLI_AGLAR:
        try:
            ip = ipaddress.ip_address(request.remote_addr or "")
        except ValueError:
            return Response("Erişim engellendi.", 403)
        if not any(ip in ag for ag in IZINLI_AGLAR):
            log.warning("İzinsiz ağdan erişim denemesi: %s", request.remote_addr)
            return Response("Erişim engellendi.", 403)
    if GIRIS_KULLANICI:
        a = request.authorization
        if not (a and secrets.compare_digest(a.username or "", GIRIS_KULLANICI)
                and secrets.compare_digest(a.password or "", GIRIS_SIFRE)):
            return Response("Giriş gerekli.", 401, {"WWW-Authenticate": 'Basic realm="Rapor"'})


@app.after_request
def guvenlik_basliklari(r):
    r.headers.setdefault("X-Content-Type-Options", "nosniff")
    r.headers.setdefault("X-Frame-Options", "DENY")
    r.headers.setdefault("Referrer-Policy", "no-referrer")
    r.headers.setdefault("Cache-Control", "no-store")   # hasta listeleri tarayıcı önbelleğinde kalmasın
    return r


@app.errorhandler(Exception)
def beklenmeyen_hata(e):
    # Ayrıntı sadece sunucu konsoluna yazılır; tarayıcıya iç bilgi gönderilmez.
    log.exception("Beklenmeyen hata")
    return jsonify(hata="Beklenmeyen bir hata oluştu. Ayrıntı sunucu kayıtlarında."), 500


# ----------------------------------------------------------------------------
# VERİTABANI
# ----------------------------------------------------------------------------
def pool():
    global _pool
    if _pool is None:
        import oracledb
        istemci = DB.get("istemci_klasoru", "").strip()
        if istemci:  # eski Oracle sürümleri (11g ve öncesi) Instant Client ister
            oracledb.init_oracle_client(lib_dir=istemci)
        sunucu, port = DB["sunucu"].strip(), int(DB.get("port", "1521"))
        sid = DB.get("sid", "").strip()
        dsn = (oracledb.makedsn(sunucu, port, sid=sid) if sid
               else oracledb.makedsn(sunucu, port, service_name=DB["servis_adi"].strip()))
        _pool = oracledb.create_pool(user=DB["kullanici"], password=DB["sifre"], dsn=dsn,
                                     min=1, max=4, increment=1)
    return _pool


def sorgula(sql, **parametreler):
    """SELECT çalıştırır, satırları liste olarak döndürür."""
    with pool().acquire() as conn, conn.cursor() as cur:
        cur.execute(sql, **parametreler)
        return [list(r) for r in cur]


def veritabani_hatasi_mi(e):
    return type(e).__module__.startswith("oracledb")


# ----------------------------------------------------------------------------
# RAPOR VERİSİ
# ----------------------------------------------------------------------------
TUM_RAPORLAR = {**raporlar.RAPORLAR, **raporlar.ALT_RAPORLAR}


def tarih_coz(s):
    """'2026-07-01T00:00:00', '2026-07-01T00:00' veya '2026-07-01' kabul eder."""
    s = s.strip().replace(" ", "T")
    for f in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, f)
        except ValueError:
            pass
    raise ValueError("Tarih biçimi anlaşılamadı.")


def verileri_getir(args):
    kod = args.get("rapor", "")
    if kod not in TUM_RAPORLAR:
        raise ValueError("Geçersiz rapor.")
    rapor = TUM_RAPORLAR[kod]
    if rapor.get("tarihsiz"):                     # anlık rapor (ör. stok): tarih yok
        tar1 = tar2 = None
    else:
        tar1 = tarih_coz(args["baslangic"])
        tar2 = tarih_coz(args["bitis"])
        if len(args["bitis"].strip()) == 10:      # sadece gün verildiyse günün sonu
            tar2 += timedelta(days=1, seconds=-1)
        if tar2 < tar1:
            raise ValueError("Bitiş tarihi başlangıçtan önce olamaz.")

    if DEMO:
        satirlar, toplam = raporlar.demo_veri(kod, tar1, tar2)
        return rapor, satirlar, toplam

    p = {} if rapor.get("tarihsiz") else {"hastane_no": HASTANE_NO, "tar1": tar1, "tar2": tar2}
    satirlar = sorgula(rapor["sql"], **p)
    toplam = None
    if rapor.get("toplam_sql"):
        toplam = [int(x or 0) for x in sorgula(rapor["toplam_sql"], **p)[0]]
    return rapor, satirlar, toplam


def deger_yaz(v, tip):
    if v is None:
        return None
    if tip == "tarih" and isinstance(v, datetime):
        return v.strftime("%d.%m.%Y %H:%M")
    if tip == "gun" and isinstance(v, datetime):
        return v.strftime("%d.%m.%Y")
    if tip == "ondalik":
        return round(float(v), 2)
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


# ----------------------------------------------------------------------------
# SAYFALAR
# ----------------------------------------------------------------------------
@app.route("/")
def ana_sayfa():
    s = raporlar.SAYFA
    menu = [{"kod": k, "menu": r["menu"], "alt": r["alt"], "aciklama": r["aciklama"],
             "tarih_etiketi": r.get("tarih_etiketi", ""), "kopyala": r.get("kopyala"),
             "tikla_kopyala": r.get("tikla_kopyala"), "tarihsiz": r.get("tarihsiz"),
             "sayac_gizle": r.get("sayac_gizle"), "ara_etiketi": r.get("ara_etiketi"),
             "ara_ipucu": r.get("ara_ipucu"), "ara_hiza": r.get("ara_hiza"),
             "renk": r.get("renk", "#1f4e5f"), "ikon": r.get("ikon", "📄")}
            for k, r in raporlar.RAPORLAR.items()]
    baslik = APP.get("baslik", "").strip() or s["baslik"]
    alt = s["alt"] + ("  ·  DEMO VERİSİ" if DEMO else "")
    return render_template("index.html", menu=menu, sayfa={**s, "alt": alt}, baslik=baslik)


@app.route("/api/liste")
def api_liste():
    try:
        rapor, satirlar, toplam = verileri_getir(request.args)
    except (KeyError, ValueError) as e:
        return jsonify(hata=str(e) or "Tarihleri kontrol edin."), 400
    except Exception as e:
        if veritabani_hatasi_mi(e):
            log.exception("Veritabanı hatası")
            return jsonify(hata="Veritabanına bağlanılamadı ya da sorgu çalışmadı. Ayrıntı sunucu kayıtlarında."), 500
        raise
    kol = rapor["kolonlar"]
    ozet = raporlar.ozet_hesapla(rapor, satirlar, toplam)
    satirlar = [[deger_yaz(v, kol[i][1]) for i, v in enumerate(r)] for r in satirlar]
    altlar = [{**{k: v for k, v in a.items() if k != "sira"},
               "adet": toplam[a["sira"]] if toplam else 0}
              for a in rapor.get("alt_listeler", [])]
    return jsonify(kolonlar=[{"ad": a, "tip": t} for a, t, _ in kol],
                   adet=len(satirlar), satirlar=satirlar, ozet=ozet, alt_listeler=altlar,
                   detay=rapor.get("detay"))


@app.route("/excel")
def excel():
    try:
        rapor, satirlar, toplam = verileri_getir(request.args)
    except (KeyError, ValueError) as e:
        return f"Excel oluşturulamadı: {e}", 400

    baslik = f'{rapor["menu"]} - {rapor["alt"]}'
    kol = rapor["kolonlar"]
    wb = Workbook()
    ws = wb.active
    ws.title = re.sub(r'[\\/*?:\[\]]', '-', rapor["alt"])[:31] or "Liste"
    if rapor.get("tarihsiz"):
        ws.append([f'{baslik}  ({datetime.now():%d.%m.%Y %H:%M} itibarıyla)'])
    else:
        t1, t2 = tarih_coz(request.args["baslangic"]), tarih_coz(request.args["bitis"])
        ws.append([f'{baslik}  ({t1:%d.%m.%Y %H:%M:%S} - {t2:%d.%m.%Y %H:%M:%S})'])
    ws["A1"].font = Font(bold=True, size=13)
    ozet = raporlar.ozet_hesapla(rapor, satirlar, toplam)
    if ozet:
        ws.append(["TOPLAM: " + "   ".join(f'{o["ad"]}: {o["deger"]}' for o in ozet)])
        ws["A2"].font = Font(bold=True, color="C2185B")
    ws.append(["No"] + [a for a, _, _ in kol])
    bas = ws.max_row
    for c in ws[bas]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4E5F")
        c.alignment = Alignment(horizontal="center")
    for i, r in enumerate(satirlar, 1):
        ws.append([i] + r)
    bicimler = {"tarih": "DD.MM.YYYY HH:MM", "gun": "DD.MM.YYYY", "ondalik": "0.00"}
    for j, (_, tip, gen) in enumerate(kol, 2):
        ws.column_dimensions[get_column_letter(j)].width = gen
        if tip in bicimler:
            for row in ws.iter_rows(min_row=bas + 1, min_col=j, max_col=j):
                for c in row:
                    c.number_format = bicimler[tip]
    ws.column_dimensions["A"].width = 6
    ws.freeze_panes = f"A{bas + 1}"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    ek = "" if rapor.get("tarihsiz") else f'_{request.args["baslangic"][:10]}_{request.args["bitis"][:10]}'
    return send_file(buf, as_attachment=True, download_name=f'{request.args["rapor"]}{ek}.xlsx',
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# Rapora özel ek adresler (ör. satır ayrıntısı)
if hasattr(raporlar, "rotalar_ekle"):
    raporlar.rotalar_ekle(app, sorgula, deger_yaz, lambda: DEMO)


if __name__ == "__main__":
    port = int(os.environ.get("PORT") or APP.get("port", "") or raporlar.SAYFA.get("port", 5050))
    host = APP.get("dinle", "0.0.0.0").strip() or "0.0.0.0"
    print(f"{raporlar.SAYFA['baslik']} çalışıyor: http://<bu-bilgisayarın-ip-adresi>:{port}"
          + ("   [DEMO MODU]" if DEMO else ""))
    try:
        from waitress import serve
        serve(app, host=host, port=port, threads=4)
    except ImportError:
        app.run(host=host, port=port)
