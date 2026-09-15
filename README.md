# fonlower

TEFAS (Türkiye Elektronik Fon Alım Satım Platformu) üzerindeki yatırım fonlarını
günlük olarak takip eden, geçmiş veri üzerinden analiz/yorum sunan sistemin
veri çekme bileşeni.

Bu repo, günlük çalışan bir cloud routine tarafından kullanılır. Routine her gün:

1. Fon takip uygulamasının (Claude Artifact) veritabanından izleme listesini okur.
2. `scripts/tefas.py sync` ile TEFAS'tan güncel fiyat/büyüklük verisini çeker.
3. Yeni verileri Artifact veritabanına yazar.
4. Son verilere bakarak kısa bir Türkçe performans yorumu üretip veritabanına yazar.

## scripts/tefas.py

Bağımlılık gerektirmez (yalnızca Python standart kütüphanesi).

```bash
# Fon ara (isim veya kod)
python3 scripts/tefas.py search "Altın"

# İzleme listesindeki fonların son N gününü çek
echo '[{"code":"AFA","kind":"YAT"}]' | python3 scripts/tefas.py sync --watchlist - --days 10
```

`kind` alanı TEFAS fon tipini belirtir: `YAT` (yatırım), `EMK` (emeklilik),
`BYF` (borsa yatırım), `GYF` (gayrimenkul yatırım), `GSYF` (girişim sermayesi).

TEFAS API'si ~6 istek/dakika ile sınırlıdır; script istekler arasında otomatik
bekleme uygular.
