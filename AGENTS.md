# Instrucciones para agentes de IA

Antes de hacer cualquier cosa en este repositorio, **lee completo `CONTEXTO.md`**. Contiene las reglas de negocio, el diseño de la base de datos, la arquitectura, las convenciones y el plan de 10 semanas de la Fase 1.

Reglas mínimas:
- Sigue el plan por semanas de `CONTEXTO.md` §6. Trabaja en una rama por semana o funcionalidad y abre un PR a `main`; se revisa antes del merge.
- No cambies decisiones de negocio, de BD ni de arquitectura por tu cuenta. Si algo no funciona, propónlo en el PR (ver `CONTEXTO.md` §9).
- No implementes lo marcado como ⏸ (Donadores, Abonos).
- Toda escritura pasa por `services.py`. Las vistas no modifican modelos directamente.
- El usuario personalizado (`AUTH_USER_MODEL`) debe existir antes de la primera migración.
- Ningún servicio ni definición de estudio sin pruebas.
- Nunca subas `.env`, credenciales ni datos reales de pacientes.

## Si tu tarea es solo el frontend (UI y diseño responsivo)

Además de lo anterior:

- **Stack fijo:** plantillas de Django + **CSS plano** (`static/css/`) + **HTMX** (`static/vendor/`). Sin npm, Tailwind, bundlers ni frameworks de JS. Ninguna dependencia nueva sin acordarla.
- **Qué puedes tocar:** `templates/`, `static/` y `PRODUCT.md`. En las pruebas, **solo** las comprobaciones de texto o de HTML de las pruebas de vistas (`test_vistas*.py` y similares) cuando el rediseño cambie un texto o una etiqueta.
- **Qué NO puedes tocar:** modelos, servicios, selectores, vistas, formularios de Django, URLs, migraciones y settings; tampoco las pruebas de servicios ni `apps/core/tests/test_permisos.py`. Si una pantalla necesita un dato o una URL que la vista no da, pídelo (issue o nota en el PR); no lo calcules en la plantilla.
- **Las plantillas no deciden permisos ni reglas.** Muestran lo que la vista manda (`puede_editar`, `puede_agendar`, `programada`…). No quites esas condiciones: ocultan acciones a quien no tiene el rol.
- **Datos de salud:** la página pública del formulario (`templates/formularios/publico.html` y `_publico_base.html`) nunca muestra datos del paciente.
- **Tono:** español de México, de «usted», claro y sin tecnicismos. Contexto de diseño, usuarios, colores y marca: `PRODUCT.md`.
- **Responsivo:** se usa en computadora, tablet y celular. Revisa cada pantalla a 390 px, 768 px y 1280 px, y con cada rol (usuarios de ejemplo: README, «Desarrollo local»).
- **Accesibilidad:** etiquetas en cada campo, foco visible, contraste suficiente y que todo funcione con teclado.
- **Tus tareas pendientes** están en `MEJORAS.md`, sección «Frontend».
- **Antes del PR:** `docker compose exec web pytest` y `ruff` en verde (la CI lo exige para fusionar). Una rama por tarea (`ui-...`) y PR a `main`.
