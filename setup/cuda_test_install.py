import subprocess
import sys
import re

# Versiones de PyTorch disponibles (combina stable y nightly)
# Nota: 12.8 sólo está disponible en modo nightly y 12.4 sólo en modo stable.
available_cuda_versions = [11.8, 12.4, 12.6, 12.8]

# Comandos de instalación para las versiones stable y nightly
install_commands = {
    11.8: {
        "stable": "pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118",
        "nightly": "pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu118"
    },
    12.4: {
        "stable": "pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124",
        "nightly": None  # No hay versión nightly para 12.4
    },
    12.6: {
        "stable": "pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126",
        "nightly": "pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu126"
    },
    12.8: {
        "stable": None,  # No hay versión stable para 12.8
        "nightly": "pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu128"
    }
}

def get_cuda_version():
    try:
        # Ejecutar el comando nvidia-smi
        result = subprocess.run(['nvidia-smi'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Si hay errores al ejecutar nvidia-smi, devolver una señal de error
        if result.returncode != 0:
            print("Error: No se pudo ejecutar nvidia-smi. ¿Está CUDA instalado correctamente?")
            return None

        # Capturar la salida como texto
        output = result.stdout

        # Buscar la versión de CUDA en la salida
        match = re.search(r"CUDA Version: (\d+\.\d+)", output)

        if match:
            return float(match.group(1))
        else:
            print("Error: No se pudo encontrar la versión de CUDA.")
            return None

    except FileNotFoundError:
        # Manejar el caso en que nvidia-smi no esté disponible
        print("Error: nvidia-smi no está disponible en el sistema.")
        return None

def find_closest_version(cuda_version, available_versions):
    # Encontrar la versión disponible más cercana a la detectada de CUDA
    closest_version = min(available_versions, key=lambda x: abs(x - cuda_version))
    return closest_version

def install_pytorch(version, channel="stable"):
    command = install_commands[version][channel]
    if command is None:
        print(f"No existe comando para PyTorch versión {version} en el canal {channel}.")
        return False
    try:
        # Ejecutar el comando de instalación
        print(f"Instalando PyTorch versión {version} desde el canal {channel}...")
        subprocess.run(command, shell=True, check=True)
        print("Instalación completada.")
    except subprocess.CalledProcessError as e:
        print(f"Error durante la instalación de PyTorch ({channel}):", e)
        return False
    return True

def uninstall_pytorch():
    # Comando para desinstalar PyTorch mediante pip (se fuerza la respuesta afirmativa)
    uninstall_command = "echo y | pip uninstall torch torchvision torchaudio"
    try:
        # Ejecutar el comando para desinstalar PyTorch
        print("Desinstalando PyTorch...")
        subprocess.run(uninstall_command, shell=True, check=True)
        print("Desinstalación completada.")
    except subprocess.CalledProcessError as e:
        print("Error durante la desinstalación de PyTorch:", e)

def test_torch_cuda():
    try:
        # Ejecutar el script de verificación en un proceso separado
        result = subprocess.run(['python', 'check_cuda.py'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            return result.stdout.strip() == 'True'
        else:
            print("Error al ejecutar el script de verificación:", result.stderr)
            return False
    except Exception as e:
        print(f"Error al verificar CUDA: {e}")
        return False

def try_install_version(version):
    # Primero, intentar con la versión stable si existe
    if install_commands[version]["stable"] is not None:
        if install_pytorch(version, "stable"):
            if test_torch_cuda():
                print(f"PyTorch versión stable con CUDA {version} está funcionando correctamente.")
                return True
            else:
                print("La versión stable no habilitó CUDA, se probará con la versión nightly...")
        # Desinstalar PyTorch si la versión stable falla o no activa CUDA
        uninstall_pytorch()

    # Intentar con la versión nightly (si está disponible)
    if install_commands[version]["nightly"] is not None:
        if install_pytorch(version, "nightly"):
            if test_torch_cuda():
                print(f"PyTorch versión nightly con CUDA {version} está funcionando correctamente.")
                return True
            else:
                print(f"La versión nightly de PyTorch con CUDA {version} tampoco habilitó CUDA.")
        uninstall_pytorch()
    else:
        print(f"No hay versión nightly disponible para CUDA {version}.")
    
    return False

def main():
    # Obtener la versión de CUDA
    cuda_version = get_cuda_version()
    if cuda_version is None:
        sys.exit("Proceso detenido: No se puede continuar sin CUDA.")

    # Encontrar la versión más cercana disponible de PyTorch
    closest_version = find_closest_version(cuda_version, available_cuda_versions)

    # Intentar instalar la versión más cercana de PyTorch
    if try_install_version(closest_version):
        return  # Finalizar si alguna instalación es exitosa

    # Si falla, probar con otras versiones disponibles (excluyendo la ya probada)
    remaining_versions = [v for v in available_cuda_versions if v != closest_version]
    for version in remaining_versions:
        print(f"Probando con la versión {version}...")
        if try_install_version(version):
            return  # Finalizar si alguna instalación es exitosa

    # Si ninguna versión logra habilitar CUDA
    print("No se pudo habilitar PyTorch con CUDA con ninguna de las versiones disponibles.")

if __name__ == "__main__":
    main()
