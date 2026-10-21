# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Recepcionista:** en el mostrador del laboratorio. Agenda citas en un calendario, registra pacientes, arma los pedidos de estudios a partir de la orden del doctor, asigna un químico a cada estudio y registra el estado de pago.
- **Químico:** en el laboratorio. Revisa todos los pedidos con filtros, captura resultados (el sistema hace los cálculos), completa estudios y envía los resultados.
- **Administrador:** registra usuarios y consulta reportes generales.
- **Paciente:** no inicia sesión. Solo abre una página pública por QR para llenar un formulario de su visita y recibe sus resultados.

## Product Purpose

Sistema web interno de EmbrioLab, un laboratorio clínico (estudios sanguíneos, de esperma, cultivos y otros). Reemplaza un flujo manual de papel, Google Forms, Excel, carpetas compartidas y envíos a mano por correo/WhatsApp que hoy produce errores y retrasos de días o meses. El éxito es que cada estudio pase de la cita al envío de resultados sin capturas duplicadas ni pérdidas.

## Operating Context

- Se usa en computadora de escritorio, tablet y celular (las tres confirmadas).
- Un solo laboratorio y un solo horario de atención; citas de 30 minutos.
- Datos de salud sujetos a LFPDPPP y NOM-004: la interfaz no debe exponer datos del paciente donde no corresponde (p. ej. la página pública del QR).

## Capabilities and Constraints

- Django con plantillas del servidor + HTMX; sin SPA.
- Interfaz en español de México.
- Detalle de reglas de negocio, datos y plan de trabajo: `CONTEXTO.md`.

## Brand Commitments

- Nombre: **EmbrioLab**.
- Existe un logotipo; todavía no está en el repositorio (pendiente de que lo entregue el cliente). Mientras tanto se usa el nombre en texto.
- Colores indicados por el cliente: principales `#ccccfe` y `#b57edc`; secundarios `#9d9d9b` y `#646463`.
- Tono: profesional y cálido. Claro, sin tecnicismos innecesarios.

## Evidence on Hand

Ninguna todavía: no hay logotipo en el repo, fotografías, testimonios ni cifras. No inventarlos.

## Product Principles

1. Exactitud antes que velocidad: los resultados clínicos no admiten ambigüedad.
2. Cada rol ve primero su trabajo pendiente.
3. Privacidad por defecto con los datos del paciente.
4. Reemplazar pasos manuales, no agregar nuevos.
