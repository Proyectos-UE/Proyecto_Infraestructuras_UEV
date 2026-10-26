"""Pruebas reproducibles del backtest artificial."""
from scripts.backtest import crear_casos, evaluar, comparar, resumen


def test_hay_cinco_casos_sinteticos_de_cada_tipo():
    casos = crear_casos()
    assert len(casos) == 10
    assert sum(viral for _, _, viral in casos) == 5
    assert all(len(serie) == 90 for _, serie, _ in casos)


def test_backtest_repetible():
    a = evaluar()
    b = evaluar()
    assert a.equals(b)
    assert len(a) == 10
    assert sum(a["verdadero_positivo"] + a["falso_negativo"]) == 5
    assert sum(a["falso_positivo"]) <= 5


def test_metricas_y_parametros():
    data = resumen(evaluar())
    assert data["TP"] + data["FN"] == 5
    assert data["FP"] + data["TN"] == 5
    assert len(comparar()) == 3
