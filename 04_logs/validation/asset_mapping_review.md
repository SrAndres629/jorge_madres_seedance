# Asset Mapping Review — Sprint 0A
# Proyecto: jorge_madres_seedance
# Fecha: 2026-06-02

---

## Resumen

- Archivos totales encontrados en el proyecto: **16**
- Assets esperados (canónicos): **10** (3 brand + 7 scenes)
- Archivos sin correspondencia a ningún asset canónico: **6** (5 mp3 + 1 jpg)

---

## BRAND BOARDS (3 esperados)

---

## board_a_identity_lock

- **Estado:** possible_match
- **Canónico:** `01_assets/brand/board_a_identity_lock.png`
- **Candidatos posibles:**
  - `universo/Board A — Identity Lock.png`
- **Nota:** El nombre contiene "Board A" e "Identity Lock". Coincidencia semántica alta. El nombre real usa espacios, em-dashes y capitalización distinta al canónico.

---

## board_b_performance_presence

- **Estado:** possible_match
- **Canónico:** `01_assets/brand/board_b_performance_presence.png`
- **Candidatos posibles:**
  - `universo/Board B — Performance & Presence Jorge.png`
- **Nota:** El nombre contiene "Board B", "Performance" y "Presence". Contiene texto adicional "Jorge" que no está en el canónico. Coincidencia semántica alta.

---

## board_c_world_integration

- **Estado:** possible_match
- **Canónico:** `01_assets/brand/board_c_world_integration.png`
- **Candidatos posibles:**
  - `universo/Board C — Jorge in World Cinematic Integration Board_final.png`
- **Nota:** El nombre contiene "Board C", "World" e "Integration". Contiene texto adicional significativo ("Jorge in", "Cinematic", "Board_final") que no está en el canónico. Revisión humana recomendada para confirmar si es el asset correcto o si existe otra versión.

---

## SCENE BOARDS (7 esperados)

---

## scene_01_hook_espejo_caos

- **Estado:** possible_match
- **Canónico:** `01_assets/scenes/scene_01_hook_espejo_caos.png`
- **Candidatos posibles:**
  - `sceneboard/Scene Board 01 — Hook espejo-caos.png`
- **Nota:** Correlación por número "01" y keywords "hook", "espejo", "caos". El nombre real usa "Scene Board" como prefijo y espacios con em-dashes.

---

## scene_02_dolor_tiempo

- **Estado:** possible_match
- **Canónico:** `01_assets/scenes/scene_02_dolor_tiempo.png`
- **Candidatos posibles:**
  - `sceneboard/Scene Board 02 — Dolor tiempo.png`
- **Nota:** Correlación por número "02" y keywords "dolor", "tiempo". 

---

## scene_03_agua_sudor_calor

- **Estado:** possible_match
- **Canónico:** `01_assets/scenes/scene_03_agua_sudor_calor.png`
- **Candidatos posibles:**
  - `sceneboard/Scene Board 03 — Agua_sudor_calor.png`
- **Nota:** Correlación por número "03" y keywords "agua", "sudor", "calor". Las keywords coinciden exactamente (con underscores).

---

## scene_04_dolor_precision

- **Estado:** possible_match
- **Canónico:** `01_assets/scenes/scene_04_dolor_precision.png`
- **Candidatos posibles:**
  - `sceneboard/Scene Board 04 — Dolor precisión.png`
- **Nota:** Correlación por número "04" y keywords "dolor", "precisión". El canónico usa "precision" sin tilde; el real usa "precisión" con tilde.

---

## scene_05_autoridad_jorge

- **Estado:** possible_match
- **Canónico:** `01_assets/scenes/scene_05_autoridad_jorge.png`
- **Candidatos posibles:**
  - `sceneboard/Scene Board 05 — Autoridad Jorge.png`
- **Nota:** Correlación por número "05" y keywords "autoridad", "jorge".

---

## scene_06_solucion_transformacion

- **Estado:** possible_match
- **Canónico:** `01_assets/scenes/scene_06_solucion_transformacion.png`
- **Candidatos posibles:**
  - `sceneboard/Scene Board 06 — Solución_transformación.png`
- **Nota:** Correlación por número "06" y keywords "solución", "transformación". El canónico usa "solucion" sin tilde; el real usa "Solución" con tilde.

---

## scene_07_cta

- **Estado:** possible_match
- **Canónico:** `01_assets/scenes/scene_07_cta.png`
- **Candidatos posibles:**
  - `sceneboard/Scene Board 07 — Oferta + CTA.png`
- **Nota:** Correlación por número "07" y keyword "CTA". El nombre real incluye "Oferta +" que no está en el canónico. Revisión humana recomendada: el canónico espera "cta" como descriptor único, pero el real sugiere que esta escena cubre tanto la oferta como el CTA.

---

## ARCHIVOS EXTRA (sin correspondencia canónica)

Estos archivos existen en el proyecto pero no corresponden a ninguno de los 10 assets esperados:

| Archivo | Carpeta | Tipo |
|---|---|---|
| `beat _final.mp3` | sonidos/ | Audio |
| `Confianza Tropical - Male Vocals.mp3` | sonidos/ | Audio |
| `musica_audioV130s.mp3` | sonidos/ | Audio |
| `Tropical Beauty Ad (30s).mp3` | sonidos/ | Audio |
| `Tu_Turno_de_Brillar.mp3` | sonidos/ | Audio |
| `imagen primer plano.jpg` | universo/ | Imagen |

---

## Notas finales

- **Ningún archivo tiene coincidencia exacta de nombre** con el canónico. Todos los assets esperados están en estado `possible_match` porque los nombres reales usan un formato distinto (espacios, em-dashes, capitalización, prefijos como "Scene Board" y "Board") frente al formato canónico (snake_case, sin prefijos).
- Las 7 scene boards y los 3 brand boards tienen **exactamente un candidato cada uno**, lo cual es una señal fuerte de que los archivos correctos ya existen pero requieren renombrado.
- Se recomienda que un humano revise y confirme las correspondencias antes de proceder al renombrado.
- Los 5 archivos `.mp3` en `sonidos/` y el archivo `imagen primer plano.jpg` en `universo/` no tienen correspondencia en los 10 assets canónicos esperados. Se dejan documentados para decisión futura.

---

**No se renombró, movió, copió ni eliminó ningún archivo. No se llamó a Kie. No se gastaron créditos.**
