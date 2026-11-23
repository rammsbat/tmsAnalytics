import datetime as dt

import pytest

from src.contract import ContractError, parse_ddl, validate_rows

AUDIT = {"BATCH_ID": "B1", "INGESTED_AT": dt.datetime(2026, 11, 6), "SOURCE_SYSTEM": "FLOTA"}


def test_contract_parses_eight_tables(contract):
    assert set(contract) == {
        "STG_TRACKIT_DESPACHO", "STG_TRACKIT_PARADAS", "STG_CARTA_PORTE_CABECERA",
        "STG_CARTA_PORTE_MERCANCIAS", "STG_FLOTA_UNIDADES", "STG_FLOTA_ESTATUS_DIARIO",
        "STG_CFDI_INGRESO", "STG_LIQUIDACIONES_GASTOS",
    }


def test_every_table_has_audit_columns(contract):
    for t in contract.values():
        names = t.column_names
        assert names[-3:] == ("BATCH_ID", "INGESTED_AT", "SOURCE_SYSTEM"), t.name


def test_flota_columns_match_ddl(contract):
    t = contract["STG_FLOTA_UNIDADES"]
    cols = {c.name: c for c in t.columns}
    assert len(t.columns) == 20
    assert (cols["CODIGO_ECO"].type, cols["CODIGO_ECO"].length, cols["CODIGO_ECO"].nullable) == ("VARCHAR2", 20, False)
    assert cols["PLACA"].nullable and cols["PLACA"].length == 20
    assert (cols["ANIO_MODELO"].precision, cols["ANIO_MODELO"].scale) == (4, 0)
    assert (cols["PESO_BRUTO_MAX_KG"].precision, cols["PESO_BRUTO_MAX_KG"].scale) == (12, 2)
    assert cols["VIGENCIA_POLIZA"].type == "DATE"
    assert cols["INGESTED_AT"].type == "TIMESTAMP" and not cols["INGESTED_AT"].nullable
    assert cols["BATCH_ID"].length == 64


def _good_row(contract):
    t = contract["STG_FLOTA_UNIDADES"]
    row = {c.name: None for c in t.columns}
    row.update({"CODIGO_ECO": "ECO01", "TIPO_UNIDAD": "TRACTOCAMION", "ESTATUS_INVENTARIO": "ACTIVO", **AUDIT})
    return t, row


def test_valid_row_passes(contract):
    t, row = _good_row(contract)
    validate_rows(t, [row])


@pytest.mark.parametrize("field,value,fragment", [
    ("CODIGO_ECO", None, "NOT NULL"),
    ("CODIGO_ECO", "E" * 21, "exceden VARCHAR2(20)"),
    ("CODIGO_ECO", "Ñ" * 11, "bytes"),            # 11 chars = 22 bytes UTF-8 > 20
    ("CODIGO_ECO", "", "vacia"),
    ("ANIO_MODELO", 20260, "excede NUMBER(4,0)"),
    ("PESO_BRUTO_MAX_KG", 1.234, "decimales"),
    ("PESO_BRUTO_MAX_KG", "29685", "se esperaba numero"),
    ("VIGENCIA_POLIZA", "2026-11-06", "date"),
    ("INGESTED_AT", dt.date(2026, 11, 6), "datetime"),
])
def test_invalid_values_are_rejected(contract, field, value, fragment):
    t, row = _good_row(contract)
    row[field] = value
    with pytest.raises(ContractError) as exc:
        validate_rows(t, [row])
    assert fragment in str(exc.value)


def test_missing_and_extra_columns_rejected(contract):
    t, row = _good_row(contract)
    row.pop("PLACA")
    row["EXTRA"] = 1
    with pytest.raises(ContractError) as exc:
        validate_rows(t, [row])
    assert "faltantes" in str(exc.value) and "extra" in str(exc.value)


def test_parse_ddl_detects_truncated_table():
    with pytest.raises(ContractError):
        parse_ddl("CREATE TABLE STG_SRC.X (\n  A VARCHAR2(5) NOT NULL,\n")
