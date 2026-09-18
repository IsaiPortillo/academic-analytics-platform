"""Hash y verificación de contraseñas.

Se usa bcrypt directamente en lugar de passlib: passlib 1.7.4 es incompatible
con bcrypt >= 4.x (lee bcrypt.__about__, que fue eliminado) y emite errores al
detectar la versión.
"""

import bcrypt

# Coste 12: ~250ms por verificación en hardware típico. Suficiente para frenar
# fuerza bruta sin afectar la experiencia de un login interno.
ROUNDS = 12


def hashear_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=ROUNDS))
    return hashed.decode("utf-8")


def verificar_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Hash malformado en la base: se trata como credencial inválida.
        return False
