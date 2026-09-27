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
