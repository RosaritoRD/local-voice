"""Tests del motor que no necesitan los modelos (validación y nombres).

    python3 -m unittest discover -s tests
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

_TMP = tempfile.mkdtemp()
os.environ["VOZ_MODELS"] = _TMP
os.environ["VOZ_SALIDA"] = str(Path(_TMP) / "salida")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import motor  # noqa: E402

(Path(_TMP) / "piper").mkdir()
(Path(_TMP) / "piper" / "es_ES-davefx-medium.onnx").write_bytes(b"")


class Limpieza(unittest.TestCase):
    def test_quita_marcas_de_guion_y_conserva_parrafos(self):
        t = motor._limpia('Hola <break time="0.4s" /> mundo [slow].\n\n**Amén**')
        self.assertEqual(t, "Hola mundo .\n\nAmén")


class Validacion(unittest.TestCase):
    def test_formato_desconocido_es_un_error(self):
        with self.assertRaisesRegex(ValueError, "Formato"):
            motor.genera("hola", "piper", formato="ogg")

    def test_voz_piper_no_puede_salir_de_la_carpeta(self):
        with self.assertRaisesRegex(ValueError, "Voz desconocida"):
            motor.genera("hola", "piper", voz="../piper/es_ES-davefx-medium")

    def test_voz_kokoro_desconocida(self):
        with self.assertRaisesRegex(ValueError, "Voz desconocida"):
            motor.genera("hola", "kokoro", voz="xx")

    def test_texto_vacio_tras_limpiar(self):
        with self.assertRaisesRegex(ValueError, "No hay texto"):
            motor.genera("<break/> [slow]", "piper")


class Nombres(unittest.TestCase):
    def test_dos_audios_seguidos_nunca_comparten_nombre(self):
        nombres = {motor._nombre_base() for _ in range(500)}
        self.assertEqual(len(nombres), 500)

    def test_el_nombre_lo_encuentra_el_historial(self):
        self.assertTrue(motor._nombre_base().startswith("voz_"))


if __name__ == "__main__":
    unittest.main()
