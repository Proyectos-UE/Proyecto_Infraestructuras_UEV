"""Validación de carga local de CSV de Google Trends."""
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pytest

from scripts.importar_trends_csv import importar
from trendwatch.models import Base, Observation
from trendwatch.services import InvalidSourceData


@pytest.fixture
def sesion():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        yield session
    engine.dispose()


def test_importar_csv_y_repetir_sin_duplicados(tmp_path, sesion):
    archivo = tmp_path / "trends.csv"
    archivo.write_text("Día,mini proyectores\n2026-10-01,25\n2026-10-08,60\n", encoding="utf-8")
    assert importar(sesion, archivo, "mini proyectores") == 2
    assert importar(sesion, archivo, "mini proyectores") == 2
    assert sesion.scalar(select(func.count()).select_from(Observation)) == 2


def test_importar_csv_invalido_no_escribe(tmp_path, sesion):
    archivo = tmp_path / "invalido.csv"
    archivo.write_text("Día,mini proyectores\n2026-10-01,120\n", encoding="utf-8")
    with pytest.raises(InvalidSourceData):
        importar(sesion, archivo, "mini proyectores")
    assert sesion.scalar(select(func.count()).select_from(Observation)) == 0


def test_csv_fecha_incorrecta_no_se_importa(tmp_path, sesion):
    archivo = tmp_path / "fecha_invalida.csv"
    archivo.write_text("Día,producto\nno-es-una-fecha,30\n", encoding="utf-8")
    with pytest.raises(ValueError):
        importar(sesion, archivo, "producto")
    assert sesion.scalar(select(func.count()).select_from(Observation)) == 0


def test_csv_fechas_duplicadas_no_se_importa(tmp_path, sesion):
    archivo = tmp_path / "duplicados.csv"
    archivo.write_text("Día,producto\n2026-10-01,30\n2026-10-01,40\n", encoding="utf-8")
    with pytest.raises(InvalidSourceData):
        importar(sesion, archivo, "producto")
    assert sesion.scalar(select(func.count()).select_from(Observation)) == 0
