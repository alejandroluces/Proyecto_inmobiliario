# Mejoras de inversion inmobiliaria

Este proyecto ya no ordena las oportunidades solo por descuento frente al precio medio de zona. El scoring ahora combina varias senales practicas para priorizar propiedades que merecen revision rapida.

## Cambios aplicados

- `opportunity_score` sigue siendo de 0 a 100, pero ahora parte de un score base por precio/m2 y se ajusta con:
  - bonus por posible contacto directo en Facebook
  - bonus por bajadas de precio detectadas en `price_history`
  - penalizacion si falta zona
  - penalizacion si faltan URL o imagenes
- Se anaden explicaciones:
  - `investment_tags`: etiquetas como `below_market`, `deep_discount`, `direct_lead`, `price_drop`
  - `opportunity_reason`: texto corto que explica por que la propiedad ha recibido esa puntuacion
- El dashboard muestra la razon y hasta tres etiquetas en cada tarjeta.
- `.gitignore` protege `.env`, sesiones de navegador, caches HTML/JSON y logs de scrapers.
- Se anaden `.env.example` para frontend y scrapers.

## Actualizacion necesaria en Supabase

Ejecuta de nuevo `services/database/schema.sql` en el SQL Editor de Supabase. Es seguro para una base ya creada porque las columnas nuevas usan `add column if not exists`.

Columnas nuevas:

```sql
investment_tags text[] default '{}'
opportunity_reason text
```

## Como interpretar el score

- `85-100`: revisar inmediatamente. Puede haber descuento fuerte, contacto directo o bajada relevante.
- `70-84`: buena candidata, pero necesita validacion manual.
- `50-69`: interesante solo si encaja con una estrategia concreta.
- `<50`: probablemente no es prioridad salvo que tenga un factor externo no capturado.

## Siguiente salto recomendado

Para que la herramienta se adelante de verdad a competidores, el siguiente bloque deberia ser un modelo financiero:

- coste de compra completo
- ITP, notaria, registro y gestoria
- reforma estimada
- alquiler mensual esperado
- gastos de comunidad, IBI, seguro y mantenimiento
- rentabilidad bruta y neta
- cashflow mensual
- margen estimado de reventa

Con eso, el ranking dejaria de decir solo "barato frente a la media" y empezaria a decir "operacion con margen probable".
