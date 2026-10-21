def usuario_para_axes(request, credenciales):
    """Correo normalizado, para que cambiar mayúsculas no reinicie el conteo de intentos."""
    correo = (credenciales or {}).get('username') or request.POST.get('username', '')
    return correo.strip().lower()
