# -*- coding: utf-8 -*-
"""
Demo modu için uydurma veri üreticisi. Gerçek kişi ya da kayıt içermez.
Hasta adları ekranda maskeli görünür (ör. "Ay*** Yı***").
"""
import random
from datetime import datetime, timedelta

_ADLAR = ["Ayşe", "Mehmet", "Fatma", "Ahmet", "Zeynep", "Mustafa", "Elif", "Hüseyin", "Emine",
          "Ali", "Hatice", "Hasan", "Merve", "İbrahim", "Selin", "Murat", "Derya", "Kemal"]
_SOYADLAR = ["Yılmaz", "Kaya", "Demir", "Şahin", "Çelik", "Yıldız", "Aydın", "Öztürk", "Arslan",
             "Doğan", "Kılıç", "Aslan", "Koç", "Kurt", "Özdemir", "Polat", "Erdoğan", "Güneş"]
DOKTORLAR = ["Dr. Örnek Hekim 1", "Dr. Örnek Hekim 2", "Dr. Örnek Hekim 3", "Dr. Örnek Hekim 4"]
ANESTEZISTLER = ["Dr. Örnek Anestezist 1", "Dr. Örnek Anestezist 2"]
OPERASYONLAR = ["Fakoemülsifikasyon + GİL implantasyonu", "Pars plana vitrektomi",
                "İntravitreal enjeksiyon", "Trabekülektomi", "Pterjium eksizyonu + otogreft",
                "Şaşılık cerrahisi", "Septoplasti", "Tonsillektomi"]


def tohum(anahtar):
    """Aynı rapor için her seferinde aynı demo verisi gelsin."""
    return random.Random(str(anahtar))


def maskeli_ad(r):
    a, s = r.choice(_ADLAR), r.choice(_SOYADLAR)
    return f"{a[:2]}*** {s[:2]}***"


def tarih(r, t1=None, t2=None):
    t2 = t2 or datetime.now()
    t1 = t1 or (t2 - timedelta(days=30))
    saniye = max(int((t2 - t1).total_seconds()), 1)
    d = t1 + timedelta(seconds=r.randrange(saniye))
    return d.replace(hour=r.randint(8, 17), minute=r.choice([0, 10, 15, 20, 30, 40, 45, 50]), second=0)


def numara(r, bas, bit):
    return r.randint(bas, bit)
