import datetime
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection
from django.test import RequestFactory

from apps.core.limites import agotado, ip_cliente, limpiar_vencidos, registrar_intento
from apps.core.models import ContadorIntentos

pytestmark = pytest.mark.django_db

UN_MINUTO = datetime.timedelta(minutes=1)


def test_cuenta_hasta_el_maximo():
    resultados = [registrar_intento('prueba', maximo=3, ventana=UN_MINUTO) for _ in range(5)]
    assert resultados == [False, False, False, True, True]
    assert agotado('prueba', maximo=3, ventana=UN_MINUTO)


def test_agotado_al_llegar_al_maximo():
    for _ in range(2):
        registrar_intento('prueba', maximo=3, ventana=UN_MINUTO)
    assert not agotado('prueba', maximo=3, ventana=UN_MINUTO)
    registrar_intento('prueba', maximo=3, ventana=UN_MINUTO)
    assert agotado('prueba', maximo=3, ventana=UN_MINUTO)


def test_claves_independientes():
    for _ in range(4):
        registrar_intento('a', maximo=3, ventana=UN_MINUTO)
    assert registrar_intento('b', maximo=3, ventana=UN_MINUTO) is False


def test_la_ventana_se_reinicia():
    for _ in range(4):
        registrar_intento('prueba', maximo=3, ventana=UN_MINUTO)
    ContadorIntentos.objects.update(
        inicio_ventana=ContadorIntentos.objects.get().inicio_ventana - UN_MINUTO
    )
    assert registrar_intento('prueba', maximo=3, ventana=UN_MINUTO) is False
    assert ContadorIntentos.objects.get().conteo == 1


def test_agotado_no_cuenta():
    agotado('prueba', maximo=3, ventana=UN_MINUTO)
    assert not ContadorIntentos.objects.exists()


def test_limpiar_vencidos():
    registrar_intento('vieja', maximo=3, ventana=UN_MINUTO)
    registrar_intento('nueva', maximo=3, ventana=UN_MINUTO)
    ContadorIntentos.objects.filter(clave='vieja').update(
        inicio_ventana=ContadorIntentos.objects.get(clave='vieja').inicio_ventana
        - datetime.timedelta(days=2)
    )
    assert limpiar_vencidos() == 1
    assert list(ContadorIntentos.objects.values_list('clave', flat=True)) == ['nueva']


@pytest.mark.django_db(transaction=True)
def test_es_atomico_con_peticiones_simultaneas():
    def intento(_):
        try:
            return registrar_intento('simultaneo', maximo=1000, ventana=UN_MINUTO)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=8) as hilos:
        list(hilos.map(intento, range(40)))
    assert ContadorIntentos.objects.get(clave='simultaneo').conteo == 40


def test_ip_directa():
    request = RequestFactory().get('/', REMOTE_ADDR='198.51.100.7')
    assert ip_cliente(request) == '198.51.100.7'


def test_ip_desde_proxy_toma_la_que_agrego_nginx(settings):
    settings.IP_DESDE_PROXY = True
    request = RequestFactory().get(
        '/', REMOTE_ADDR='172.18.0.5', HTTP_X_FORWARDED_FOR='1.2.3.4, 198.51.100.7'
    )
    assert ip_cliente(request) == '198.51.100.7'


def test_sin_proxy_ignora_x_forwarded_for():
    request = RequestFactory().get('/', REMOTE_ADDR='198.51.100.7', HTTP_X_FORWARDED_FOR='1.2.3.4')
    assert ip_cliente(request) == '198.51.100.7'
