# -*- coding: utf-8 -*-
"""
Güvenli Cerrahi Kontrol Listesi Denetimi (SKS gösterge kodu: TIPM.GKG13).

Seçilen dönemdeki TÜM ameliyatları tarar; güvenli cerrahi göstergesine giren
alanlardan biri atlanmış olanları listeler. Ayrıca HBYS gösterge kartının
pay / payda / oran değerlerini aynı formülle hesaplar ve ÜTS (Ürün Takip
Sistemi) kullanım bildirimi eksik lensleri bulur. Yalnızca okuma (SELECT) yapar.

Sorgular HBYS'nin Oracle veritabanındaki HASTANE şemasına göre yazılmıştır.
Farklı bir HBYS'de tablo / kolon adlarını kendi şemanıza göre uyarlayın.
"""
import math

import demo

SAYFA = {"baslik": "Güvenli Cerrahi Denetimi", "alt": "SKS güvenli cerrahi göstergesi · eksik kayıt listeleri",
         "ikon": "🩺", "renk1": "#0b3d4f", "renk2": "#0f8b8d", "port": 5051}

# ----------------------------------------------------------------------------
# Güvenli cerrahi (SKS TIPM.GKG13) - eksik / atlanmış kayıtlar.
# HBYS gösterge kartının baktığı alanlar (form maddelerine bakmaz):
#   AMELIYATHANE.SKS_GOZLEM_YAPILDI = 'T'  -> paydaya girer
#   AMELIYATHANE.SKS_KONTROL_UYGUN  = 'T'  -> paya girer
# HBYS'nin detay listesi ayrıca INDIKATOR_CERR_KONTROL formu girilmiş
# ameliyatları gösterir. Burada dönemdeki TÜM ameliyatlar taranır ve bu üç
# şeyden biri eksik olanlar listelenir. Liste boşsa her şey tamamdır.
# "Sorun" kolonunda birden fazla sorun "; " ile ayrılır (ekranda ayrı etiket olur).
#
# İntravitreal enjeksiyon (lazer) hastalarının hepsi ameliyat defterine yazılmaz.
# Bu yüzden bu işlem sadece protokole aşağıdaki ilaçlardan biri yazılmışsa
# (V_HAREKET'te barkodu varsa) listelenir. Yeni ilaç eklemek için barkodunu
# listeye eklemeniz yeterlidir.
INTRAVITREAL_KODU = 80   # AMELIYAT_LIST: İntravitreal ponksiyon ve/veya injeksiyonu
INTRAVITREAL_ILACLAR = {
    "8699505762821": "ALTUZAN 100 MG 4 ML",
    "8699546959358": "EYLEA 40 MG/ML 1 FLAKON",
    "8699546770069": "EYLEA HD INTRAVITREAL FLK",
    "8699514770008": "YESAFILI 40 MG 1 ML 1 FLK",
    "8699505773759": "VABYSMO 6MG/0.05ML INTRAVITREAL ENJEKSIYON",
}
_BARKODLAR = ", ".join(f"'{b}'" for b in INTRAVITREAL_ILACLAR)

_CERRAHI_T = f"""
  SELECT A.DOSYA_NO,
         K.ADI || ' ' || K.SOYADI           HASTA,
         A.PROTOKOL_NO,
         A.BAS_TARIHI,
         DR.ADI_SOYADI                       DOKTOR,
         OPL.OPERASYON_ADI,
         NVL(A.SKS_GOZLEM_YAPILDI, 'F')      GOZLEM,
         NVL(A.SKS_KONTROL_UYGUN, 'F')       UYGUN,
         CASE WHEN EXISTS (SELECT 1 FROM HASTANE.INDIKATOR_CERR_KONTROL I
                           WHERE I.PROTOKOL_NO = A.PROTOKOL_NO)
              THEN 'T' ELSE 'F' END          FORM,
         -- ameliyat ekranında operasyon seçilmemişse AMELIYAT_YAP kaydı olmaz;
         -- bu ameliyatlar HBYS göstergesinde hiç görünmez (pay ve paydaya girmez)
         CASE WHEN AME.PROTOKOL_NO IS NULL THEN 'F' ELSE 'T' END ISLEM
  FROM HASTANE.AMELIYATHANE A
  LEFT JOIN HASTANE.AMELIYAT_YAP AME
       ON  AME.DOSYA_NO    = A.DOSYA_NO
       AND AME.PROTOKOL_NO = A.PROTOKOL_NO
       AND AME.SIRA_NO     = A.SIRA_NO
  LEFT JOIN HASTANE.AMELIYAT_LIST OPL ON OPL.OPERASYON_KODU = AME.OPERASYON_KODU
  LEFT JOIN HASTANE.KIMLIK K          ON K.DOSYA_NO  = A.DOSYA_NO
  LEFT JOIN HASTANE.DRADI DR          ON DR.DR_KODU  = A.OPERATOR_DR
  WHERE A.BAS_TARIHI >= :tar1
    AND A.BAS_TARIHI <= :tar2
    AND A.HASTANE_NO = :hastane_no
    -- operasyonu girilmemiş kayıtlar ancak şu durumlarda gerçek işlem sayılır:
    --   * güvenli cerrahi süreci başlamış (gözlem işaretli ya da kontrol formu girilmiş)
    --   * protokole intravitreal ilaç yazılmış (ilaçlı enjeksiyon yapılmış)
    -- hiçbiri yoksa ilaçsız lazer / iptal / boş kayıttır, listeye alınmaz
    AND (AME.PROTOKOL_NO IS NOT NULL
         OR A.SKS_GOZLEM_YAPILDI = 'T'
         OR EXISTS (SELECT 1 FROM HASTANE.INDIKATOR_CERR_KONTROL I2
                    WHERE I2.PROTOKOL_NO = A.PROTOKOL_NO)
         OR EXISTS (SELECT 1 FROM HASTANE.V_HAREKET H2
                    WHERE H2.PROTOKOL_NO = A.PROTOKOL_NO
                      AND H2.BARKOD IN ({_BARKODLAR})))
    -- intravitreal enjeksiyon sadece ilaç yazılmışsa (lazer hastaları gelmesin)
    AND (NVL(AME.OPERASYON_KODU, -1) <> {INTRAVITREAL_KODU}
         OR EXISTS (SELECT 1 FROM HASTANE.V_HAREKET H
                    WHERE H.PROTOKOL_NO = A.PROTOKOL_NO
                      AND H.BARKOD IN ({_BARKODLAR})))"""

# İlaç yazılmamış intravitreal enjeksiyon (lazer) satırı
_ILACSIZ_LAZER = f"""(AME.OPERASYON_KODU = {INTRAVITREAL_KODU}
              AND NOT EXISTS (SELECT 1 FROM HASTANE.V_HAREKET H
                              WHERE H.PROTOKOL_NO = A.PROTOKOL_NO
                                AND H.BARKOD IN ({_BARKODLAR})))"""

# Özet kutuları için toplamlar (sıra önemli, ozet_hesapla ve alt_listeler kullanır):
#  4) ÜTS kullanım bildirimi eksik lens sayısı (CERRAHI_UTS_SQL listesi)
#  0) dönemdeki tüm (filtreye uyan) ameliyat satırı sayısı
#  1-2) HBYS gösterge kartının pay ve paydası, HBYS'nin kendi formülüyle
#       (gözlem yapılmış satırlar; lazer filtresi yok, her işlem ayrı satır)
#  3) bu paydanın içindeki ilaçsız lazer satırları (CERRAHI_LAZER_SQL listesi)
# ÜTS kullanım bildirimi: Sağlık Bakanlığı, hastaya takılan lenslerin ÜTS'ye bildirilmesini
# istiyor. Payda (gözlem yapılmış) protokollerinde lens depolarından hastaya çıkışı yapılan
# her lens için, HBYS işlem satırındaki (ISLEMYAP) UTS_KULLANIM_BILDIRIM_ID kontrol edilir.
# Eşleştirme (aynı protokolde, biri tutması yeterli):
#   - seri no: UTS_SERI_NO ya da karekodun içinde seri no
#   - lot no : UTS_LOT_NO
#   - ürün barkodu: işlem satırının karekodu lensin barkoduyla başlıyor
#     (HBYS bazen karekodu "barkod__" diye seri no'suz kaydediyor)
_UTS_ESLES = """I.PROTOKOL_NO = P.PROTOKOL_NO
             AND (   (H.SERI_NO IS NOT NULL
                      AND (I.UTS_SERI_NO = H.SERI_NO OR I.KAREKOD LIKE '%' || H.SERI_NO || '%'))
                  OR (H.LOT_NO IS NOT NULL AND I.UTS_LOT_NO = H.LOT_NO)
                  OR (H.BARKOD IS NOT NULL AND I.KAREKOD LIKE H.BARKOD || '%'))"""

_UTS_LENS = f"""
SELECT P.DOSYA_NO, P.PROTOKOL_NO, P.BAS_TARIHI,
       (SELECT MAX(M.ADI) FROM HASTANE.MALZEME M WHERE M.MALZEME_NO = H.MALZEME_NO) LENS_ADI,
       NVL(H.SERI_NO, 'Lot ' || H.LOT_NO) SERI_LOT,
       CASE WHEN EXISTS (SELECT 1 FROM HASTANE.ISLEMYAP I
                         WHERE {_UTS_ESLES}
                           AND I.UTS_KULLANIM_BILDIRIM_ID IS NOT NULL) THEN 'Bildirildi'
            WHEN EXISTS (SELECT 1 FROM HASTANE.ISLEMYAP I
                         WHERE {_UTS_ESLES}) THEN 'ÜTS bildirimi yapılmamış'
            ELSE 'İşlem satırında lens bulunamadı' END DURUM
FROM (SELECT A.DOSYA_NO, A.PROTOKOL_NO, MIN(A.BAS_TARIHI) BAS_TARIHI
      FROM HASTANE.AMELIYATHANE A
      JOIN HASTANE.AMELIYAT_YAP AME
           ON  AME.DOSYA_NO    = A.DOSYA_NO
           AND AME.PROTOKOL_NO = A.PROTOKOL_NO
           AND AME.SIRA_NO     = A.SIRA_NO
      WHERE A.BAS_TARIHI >= :tar1
        AND A.BAS_TARIHI <= :tar2
        AND A.HASTANE_NO = :hastane_no
        AND A.SKS_GOZLEM_YAPILDI = 'T'
        AND EXISTS (SELECT 1                      -- sadece SGK hastaları (KURUM_NO 31)
                    FROM HASTANE.PROTOKOL PR
                    JOIN HASTANE.KURUM KR ON KR.KURUM_NO = PR.KURUM_NO
                    WHERE PR.PROTOKOL_NO = A.PROTOKOL_NO
                      AND (KR.KURUM_NO = 31 OR KR.KURUM_ADI LIKE 'SGK%'))
      GROUP BY A.DOSYA_NO, A.PROTOKOL_NO) P
JOIN HASTANE.V_HAREKET H
     ON  H.PROTOKOL_NO   = P.PROTOKOL_NO
     AND H.GONDEREN_DEPO IN (16, 109)    -- Lens Ana Depo, Kat 6 Lens Depo (LENS_ANA_DEPO / LENS_KAT6_DEPO)
     AND H.ALAN_DEPO     = -1"""

CERRAHI_UTS_SQL = f"""
SELECT U.DOSYA_NO,
       U.PROTOKOL_NO,
       K.ADI || ' ' || K.SOYADI,
       U.BAS_TARIHI,
       U.LENS_ADI,
       U.SERI_LOT,
       U.DURUM
FROM ({_UTS_LENS}) U
LEFT JOIN HASTANE.KIMLIK K ON K.DOSYA_NO = U.DOSYA_NO
WHERE U.DURUM <> 'Bildirildi'
ORDER BY U.BAS_TARIHI, U.PROTOKOL_NO"""


CERRAHI_TOPLAM_SQL = f"""
WITH T AS (
{_CERRAHI_T}
),
M AS (
  SELECT A.PROTOKOL_NO,
         NVL(A.SKS_KONTROL_UYGUN, 'F') UYGUN,
         CASE WHEN {_ILACSIZ_LAZER} THEN 'T' ELSE 'F' END ILACSIZ_LAZER
  FROM HASTANE.AMELIYATHANE A
  JOIN HASTANE.AMELIYAT_YAP AME
       ON  AME.DOSYA_NO    = A.DOSYA_NO
       AND AME.PROTOKOL_NO = A.PROTOKOL_NO
       AND AME.SIRA_NO     = A.SIRA_NO
  WHERE A.BAS_TARIHI >= :tar1
    AND A.BAS_TARIHI <= :tar2
    AND A.HASTANE_NO = :hastane_no
    AND A.SKS_GOZLEM_YAPILDI = 'T'
)
SELECT (SELECT COUNT(*) FROM T),
       -- pay / payda protokol bazında: aynı protokoldeki birden fazla ameliyat tek sayılır;
       -- protokol, içindeki ameliyatların hepsi uygunsa paya girer
       (SELECT COUNT(*) FROM (SELECT PROTOKOL_NO FROM M
                              GROUP BY PROTOKOL_NO HAVING MIN(UYGUN) = 'T')),
       (SELECT COUNT(DISTINCT PROTOKOL_NO) FROM M),
       (SELECT COUNT(CASE WHEN ILACSIZ_LAZER = 'T' THEN 1 END) FROM M),
       (SELECT COUNT(*) FROM ({_UTS_LENS}) U WHERE U.DURUM <> 'Bildirildi')
FROM DUAL"""


def _gosterge_sql(sadece_uygun):
    """HBYS gösterge kartının payda (gözlem yapılmış) ya da pay (+ kontrol uygun)
    hastaları. Protokol bazında: aynı protokolde birden fazla ameliyat varsa hasta
    tek satırda görünür, ameliyat adları ' + ' ile birleşir. Protokoldeki
    ameliyatların hepsi uygunsa protokol 'UYGUN' sayılır."""
    return f"""
SELECT A.DOSYA_NO,
       A.PROTOKOL_NO,
       K.ADI || ' ' || K.SOYADI,
       MIN(A.BAS_TARIHI),
       CASE WHEN MIN(NVL(A.SKS_KONTROL_UYGUN, 'F')) = 'T' THEN 'UYGUN' ELSE 'UYGUN DEĞİL' END,
       MIN(DR.ADI_SOYADI),
       LISTAGG(OPL.OPERASYON_ADI, ' + ') WITHIN GROUP (ORDER BY A.SIRA_NO)
FROM HASTANE.AMELIYATHANE A
JOIN HASTANE.AMELIYAT_YAP AME
     ON  AME.DOSYA_NO    = A.DOSYA_NO
     AND AME.PROTOKOL_NO = A.PROTOKOL_NO
     AND AME.SIRA_NO     = A.SIRA_NO
LEFT JOIN HASTANE.AMELIYAT_LIST OPL ON OPL.OPERASYON_KODU = AME.OPERASYON_KODU
LEFT JOIN HASTANE.KIMLIK K          ON K.DOSYA_NO  = A.DOSYA_NO
LEFT JOIN HASTANE.DRADI DR          ON DR.DR_KODU  = A.OPERATOR_DR
WHERE A.BAS_TARIHI >= :tar1
  AND A.BAS_TARIHI <= :tar2
  AND A.HASTANE_NO = :hastane_no
  AND A.SKS_GOZLEM_YAPILDI = 'T'
GROUP BY A.DOSYA_NO, A.PROTOKOL_NO, K.ADI, K.SOYADI
{"HAVING MIN(NVL(A.SKS_KONTROL_UYGUN, 'F')) = 'T'" if sadece_uygun else ""}
ORDER BY MIN(A.BAS_TARIHI), A.PROTOKOL_NO"""

# HBYS'nin saydığı ama bizim listenin saymadığı ilaçsız lazer hastaları
# (gözlem yapılmış intravitreal enjeksiyon, protokolde ilaç yok).
# Ekranda "İlaçsız lazer" düğmesiyle açılır.
CERRAHI_LAZER_SQL = f"""
SELECT A.DOSYA_NO,
       A.PROTOKOL_NO,
       K.ADI || ' ' || K.SOYADI,
       A.BAS_TARIHI,
       CASE WHEN NVL(A.SKS_KONTROL_UYGUN, 'F') = 'T' THEN 'UYGUN' ELSE 'UYGUN DEĞİL' END,
       DR.ADI_SOYADI,
       OPL.OPERASYON_ADI
FROM HASTANE.AMELIYATHANE A
JOIN HASTANE.AMELIYAT_YAP AME
     ON  AME.DOSYA_NO    = A.DOSYA_NO
     AND AME.PROTOKOL_NO = A.PROTOKOL_NO
     AND AME.SIRA_NO     = A.SIRA_NO
LEFT JOIN HASTANE.AMELIYAT_LIST OPL ON OPL.OPERASYON_KODU = AME.OPERASYON_KODU
LEFT JOIN HASTANE.KIMLIK K          ON K.DOSYA_NO  = A.DOSYA_NO
LEFT JOIN HASTANE.DRADI DR          ON DR.DR_KODU  = A.OPERATOR_DR
WHERE A.BAS_TARIHI >= :tar1
  AND A.BAS_TARIHI <= :tar2
  AND A.HASTANE_NO = :hastane_no
  AND A.SKS_GOZLEM_YAPILDI = 'T'
  AND {_ILACSIZ_LAZER}
ORDER BY A.BAS_TARIHI, A.PROTOKOL_NO"""

CERRAHI_EKSIK_SQL = f"""
WITH T AS (
{_CERRAHI_T}
)
SELECT DOSYA_NO,
       PROTOKOL_NO,
       HASTA,
       BAS_TARIHI,
       RTRIM(
         CASE WHEN ISLEM  <> 'T' THEN 'Operasyon girilmemiş; ' END ||
         CASE WHEN GOZLEM <> 'T' THEN 'Gözlem yapıldı işaretlenmemiş; ' END ||
         CASE WHEN FORM   <> 'T' THEN 'Kontrol listesi formu girilmemiş; ' END ||
         CASE WHEN UYGUN  <> 'T' THEN 'Kontrol uygun işaretlenmemiş; ' END
       , '; '),
       DOKTOR,
       OPERASYON_ADI
FROM T
WHERE GOZLEM <> 'T'
   OR UYGUN  <> 'T'
   OR FORM   <> 'T'
   OR ISLEM  <> 'T'
ORDER BY BAS_TARIHI, PROTOKOL_NO"""

# Ekrandaki özet kutuları için sorun adları (SQL'deki metinlerle aynı olmalı)
CERRAHI_SORUNLAR = [
    ("Operasyon girilmemiş", "Operasyon girilmemiş"),
    ("Gözlem işaretlenmemiş", "Gözlem yapıldı işaretlenmemiş"),
    ("Form girilmemiş", "Kontrol listesi formu girilmemiş"),
    ("Uygun işaretlenmemiş", "Kontrol uygun işaretlenmemiş"),
]


RAPORLAR = {
    "cerrahi_eksik": {
        "renk": "#0f8b8d", "ikon": "🩺",
        "menu": "Güvenli Cerrahi Girilmeyen Hastalar",
        "alt": "Eksik / atlanmış kontrol listesi",
        "aciklama": "Seçilen dönemdeki <b>tüm ameliyatlar</b> taranır; güvenli cerrahi göstergesine (SKS TIPM.GKG13) giren alanlardan biri "
                    "<b>atlanmış</b> olanlar listelenir: <b>Gözlem yapıldı</b> işaretlenmemiş (ameliyat göstergeye hiç girmez), "
                    "<b>Kontrol uygun</b> işaretlenmemiş (oranı düşürür), <b>kontrol listesi formu</b> girilmemiş (hasta göstergenin detay listesinde görünmez) "
                    "ya da ameliyat ekranında <b>operasyon girilmemiş</b> (ameliyat HBYS göstergesinde hiç görünmez). "
                    "<b>İntravitreal enjeksiyonlar</b> sadece protokole <b>Altuzan, Eylea, Eylea HD, Yesafili</b> ya da <b>Vabysmo</b> yazılmışsa listelenir "
                    "(ilaçsız lazer hastaları gelmez). <b>Liste boşsa her şey tamamdır.</b>",
        "tarih_etiketi": "Ameliyat",
        "kopyala": 1,
        "tikla_kopyala": [0, 1],   # Dosya No ve Protokol No tıklayınca kopyalanır
        "ozet": {"tur": "cerrahi", "sorun": 4},
        "sql": CERRAHI_EKSIK_SQL,
        "toplam_sql": CERRAHI_TOPLAM_SQL,
        # düğmeler: kod, yazı, ikon, renk, toplam_sql'deki adet sırası
        "alt_listeler": [
            {"kod": "cerrahi_lazer", "ad": "İlaçsız lazer hastaları", "ikon": "💉", "renk": "#e65100", "sira": 3},
            {"kod": "cerrahi_uts", "ad": "ÜTS bildirimi eksik lensler", "ikon": "📡", "renk": "#6a1b9a", "sira": 4},
        ],
        "kolonlar": [
            ("Dosya No", "sayi", 10), ("Protokol No", "sayi", 12), ("Hasta", "metin", 26),
            ("Ameliyat Tarihi", "tarih", 17), ("Sorun", "sorunlar", 50),
            ("Doktor", "metin", 22), ("Operasyon Adı", "metin", 40),
        ],
    },
}

# Menüde görünmeyen, bir raporun içindeki düğmeyle açılan listeler
ALT_RAPORLAR = {
    "cerrahi_lazer": {
        "menu": "Güvenli Cerrahi Girilmeyen Hastalar",
        "alt": "İlaçsız lazer hastaları (HBYS'de sayılan)",
        "tarih_etiketi": "Ameliyat",
        "sql": CERRAHI_LAZER_SQL,
        "kolonlar": [
            ("Dosya No", "sayi", 10), ("Protokol No", "sayi", 12), ("Hasta", "metin", 26),
            ("Ameliyat Tarihi", "tarih", 17), ("Kontrol Uygun mu?", "durum", 16),
            ("Doktor", "metin", 22), ("Operasyon Adı", "metin", 40),
        ],
    },
}
ALT_RAPORLAR["cerrahi_uts"] = {
    "menu": "Güvenli Cerrahi Girilmeyen Hastalar",
    "alt": "ÜTS kullanım bildirimi eksik lensler (payda hastaları, hastaya takılan lensler)",
    "tarih_etiketi": "Ameliyat",
    "sql": CERRAHI_UTS_SQL,
    "kolonlar": [
        ("Dosya No", "sayi", 10), ("Protokol No", "sayi", 12), ("Hasta", "metin", 26),
        ("Ameliyat Tarihi", "tarih", 17), ("Lens Adı", "metin", 40),
        ("Seri / Lot No", "metin", 18), ("Durum", "durum", 28),
    ],
}
# Pay / payda kutularına tıklayınca açılan listeler
for _kod, _uygun, _alt in (("cerrahi_gosterge_payda", False, "Payda hastaları (gözlem yapılmış, her protokol bir kez)"),
                           ("cerrahi_gosterge_pay", True, "Pay hastaları (gözlem yapılmış ve kontrol uygun, her protokol bir kez)")):
    ALT_RAPORLAR[_kod] = {
        "menu": "Güvenli Cerrahi Girilmeyen Hastalar",
        "alt": _alt,
        "tarih_etiketi": "Ameliyat",
        "sql": _gosterge_sql(_uygun),
        "kolonlar": ALT_RAPORLAR["cerrahi_lazer"]["kolonlar"],
    }

def ozet_hesapla(rapor, satirlar, toplam=None):
    """Listenin üstündeki kutular: gösterge pay / payda / oran ve sorun sayıları."""
    oz = rapor.get("ozet")
    if not oz or oz["tur"] != "cerrahi":
        return None
    sorunlar = [(r[oz["sorun"]] or "").split("; ") for r in satirlar]
    top_ameliyat, pay, payda = (toplam or [0] * 5)[:3]   # sıra: CERRAHI_TOPLAM_SQL
    oran = math.floor(pay / payda * 10000) / 100 if payda else 0  # gösterge kartı gibi TRUNC(..., 2)
    return [
        {"ad": "Pay (hasta)", "deger": pay, "vurgu": True,
         "alt": "cerrahi_gosterge_pay", "alt_ad": "Pay hastaları"},
        {"ad": "Payda (hasta)", "deger": payda, "vurgu": True,
         "alt": "cerrahi_gosterge_payda", "alt_ad": "Payda hastaları"},
        {"ad": "Oran (%)", "deger": oran, "vurgu": True},
        {"ad": "Toplam ameliyat", "deger": top_ameliyat},
    ] + [{"ad": ad, "deger": sum(1 for s in sorunlar if any(x.startswith(metin) for x in s))}
         for ad, metin in CERRAHI_SORUNLAR]


# ----------------------------------------------------------------------------
# DEMO VERİSİ (DEMO=1 ile veritabanısız çalıştırma)
# ----------------------------------------------------------------------------
_DEMO_SORUNLAR = ["Kontrol uygun işaretlenmemiş", "Kontrol listesi formu girilmemiş",
                  "Gözlem yapıldı işaretlenmemiş", "Operasyon girilmemiş"]
_DEMO_LENSLER = ["Hidrofobik akrilik GİL +21.5 D", "Hidrofobik akrilik GİL +22.0 D",
                 "Torik GİL +20.5 D T3", "Multifokal GİL +23.0 D"]


def demo_veri(kod, tar1, tar2):
    r = demo.tohum(kod)
    satir = lambda: [demo.numara(r, 100000, 199999), demo.numara(r, 2000000, 2999999),
                     demo.maskeli_ad(r), demo.tarih(r, tar1, tar2)]
    if kod == "cerrahi_eksik":
        satirlar = []
        for _ in range(r.randint(9, 14)):
            s = r.sample(_DEMO_SORUNLAR, r.choice([1, 1, 1, 2]))
            satirlar.append(satir() + ["; ".join(s), r.choice(demo.DOKTORLAR), r.choice(demo.OPERASYONLAR)])
        payda = r.randint(180, 240)
        pay = payda - r.randint(2, 9)
        return sorted(satirlar, key=lambda s: s[3]), [payda + len(satirlar), pay, payda, r.randint(3, 8), r.randint(1, 5)]
    if kod == "cerrahi_uts":
        return [satir() + [r.choice(_DEMO_LENSLER), f"SN{demo.numara(r, 10000000, 99999999)}",
                           "ÜTS bildirimi yapılmamış"] for _ in range(r.randint(2, 5))], None
    n = r.randint(5, 8) if kod == "cerrahi_lazer" else r.randint(20, 30)
    return [satir() + ["UYGUN" if (kod != "cerrahi_gosterge_payda" or r.random() > .1) else "UYGUN DEĞİL",
                       r.choice(demo.DOKTORLAR),
                       "İntravitreal enjeksiyon" if kod == "cerrahi_lazer" else r.choice(demo.OPERASYONLAR)]
            for _ in range(n)], None
