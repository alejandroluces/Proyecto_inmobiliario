# Idealista Manual Assist

Este flujo evita automatizar Idealista. Tu navegas Idealista de forma normal,
guardas una captura con GoFullPage si quieres dejar evidencia, y cargas los
datos visibles en JSON o TXT para que entren al mismo scoring del dashboard.

## Carpetas

- `captures/`: guarda aqui capturas GoFullPage, PNG, JPG o PDF.
- `*.json`: listados revisables que se importan al dashboard.
- `*.txt`: texto copiado/OCR separado por bloques en blanco.

## Crear plantilla

```powershell
cd "C:\Users\aleja\OneDrive\Desktop\Repositorios git\Intelligent-Asset-Tracker\services\scrapers"
python scraper_idealista_manual.py --template
```

Edita:

```text
manual_imports\idealista\idealista_manual_template.example.json
```

Cuando lo tengas listo, guardalo con otro nombre acabado en `.json`, por ejemplo
`idealista_altea_hills_2026-05-02.json`. Los archivos `.example.json` no se
importan.

## Generar JSON automaticamente desde una captura

Necesitas `OPENAI_API_KEY` en `services/scrapers/.env` y las dependencias de
`requirements.txt` instaladas.

```powershell
cd "C:\Users\aleja\OneDrive\Desktop\Repositorios git\Intelligent-Asset-Tracker\services\scrapers"
python generate_idealista_json_from_capture.py --latest
```

El script usa la captura PNG/JPG mas reciente en `captures/`, crea un JSON
`idealista_auto_*.json` y lo deja listo para revisar. Despues ejecuta:

```powershell
python scraper_idealista_manual.py --parse
python main.py --source idealista-manual
```

## Formato JSON recomendado

```json
{
  "properties": [
    {
      "title": "Casa o chalet en venta en Calle Holanda, 91, Altea Hills",
      "price": "3.990.000 EUR",
      "m2": "1065 m2",
      "zone": "Altea Hills",
      "url": "https://www.idealista.com/inmueble/123456789/",
      "description": "Texto visible o notas de la captura.",
      "capture_file": "idealista_altea_hills_2026-05-02.png",
      "images": [],
      "notes": "Pegado manual desde captura GoFullPage."
    }
  ]
}
```

## Probar sin subir a Supabase

```powershell
python scraper_idealista_manual.py --parse
```

## Subir al dashboard

Necesitas `SUPABASE_SERVICE_KEY` con role `service_role` en `services/scrapers/.env`.

```powershell
python main.py --source idealista-manual
```

## Consejos

- Usa la URL real del anuncio cuando la tengas. Si no, el importador genera un
  ID estable con titulo, precio, metros y zona.
- Revisa precios con puntos: `3.990.000 EUR` se interpreta como `3990000`.
- Si el TXT viene de OCR, revisa manualmente precio y metros antes de subir.
